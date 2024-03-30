import contextlib
import functools
import json
import operator
import queue
import socket
import subprocess
import tempfile
import threading
import typing
from pathlib import Path
from typing import Iterator

import attrs
import pysubs2  # type: ignore[import-untyped]
import rich.progress

_T = typing.TypeVar("_T")


@attrs.frozen(kw_only=True)
class Total(typing.Generic[_T]):
    name: bytes
    total: _T
    converter: typing.Callable[[str], _T]


def ensure_ffmpeg() -> bool:
    try:
        subprocess.check_call(["ffmpeg", "-version"], stdout=subprocess.PIPE)
        subprocess.check_call(["ffprobe", "-version"], stdout=subprocess.PIPE)
        return True
    except Exception:
        return False


def ffmpeg(description: str = ""):
    def decorator(f):
        nonlocal description

        if not description:
            description = f"Running {f.__name__}"

        context_manager = contextlib.contextmanager(f)

        def with_progress(total: Total | None = None, description: str = description):
            @functools.wraps(f)
            def wrapper(*args, **kwargs):
                with context_manager(*args, **kwargs) as args:
                    ffmpeg_progress(args, description=description, total=total)

            return wrapper

        def as_iterator(key: bytes, converter: typing.Callable[[bytes], _T]):
            @functools.wraps(f)
            def wrapper(*args, **kwargs):
                with context_manager(*args, **kwargs) as args:
                    yield from ffmpeg_progress_iterator(
                        args, progress_key=key, progress_converter=converter
                    )

            return wrapper

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            with context_manager(*args, **kwargs) as args:
                subprocess.run(["ffmpeg", *args], capture_output=True, check=True)

        wrapper.with_progress = with_progress  # type: ignore[attr-defined]
        wrapper.as_iterator = as_iterator  # type: ignore[attr-defined]

        return wrapper

    return decorator


def get_subtitle_stream_id(video: Path, language: str = "eng") -> int:
    """
    The subtitle stream index among subtitle streams.
    This ignores non-subtitle streams.
    """
    # First, probe the file to get the right stream
    process = subprocess.run(
        [
            "ffprobe",
            "-print_format",
            "json",
            str(video),
            "-show_streams",
            "-v",
            "error",
        ],
        capture_output=True,
        check=True,
    )
    probe = json.loads(process.stdout)

    subtitle_streams = [
        stream
        for stream in probe.get("streams", [])
        if stream.get("codec_type") == "subtitle"
    ]
    for i, stream in enumerate(subtitle_streams):
        if stream.get("tags", {}).get("language") == language:
            break
    else:
        raise RuntimeError()

    return i


def extract_subtitle_stream(
    video: Path,
    subtitle_stream_id: int,
    fmt: str = "ass",
    start: str | None = None,
    end: str | None = None,
) -> bytes:
    input_cmds = []
    if start:
        input_cmds.extend(["-ss", start])
    if end:
        input_cmds.extend(["-to", end])
    return subprocess.check_output(
        [
            "ffmpeg",
            *input_cmds,
            "-i",
            str(video),
            "-map",
            f"0:s:{subtitle_stream_id}",
            "-f",
            fmt,
            "-v",
            "quiet",
            "-",
        ]
    )


def extract_subs_by_language(video: Path, language: str = "eng", fmt="ass") -> bytes:
    subtitle_stream_id = get_subtitle_stream_id(video, language=language)

    # Then we extract it to stdout
    raw_subs = extract_subtitle_stream(video, subtitle_stream_id, fmt=fmt)
    return raw_subs


@ffmpeg()
def concat_videos(videos: list[Path], output: Path):
    concat_list = (f"file '{video.absolute()!s}'" for video in videos)
    concat_text = "\n".join(concat_list)

    with tempfile.TemporaryDirectory() as tempdir:
        list_path = Path(tempdir) / "list.txt"
        list_path.write_text(concat_text)
        yield [
            "-safe",
            "0",
            "-f",
            "concat",
            "-i",
            str(list_path),
            str(output),
        ]


def validate_video(video: Path):
    subprocess.run(["ffprobe", str(video)], capture_output=True, check=True)


@ffmpeg()
def trim_video(video: Path, start: int, end: int, output: Path):
    filter_command = (
        f"[0:v]trim={0}:{end - start}ms,setpts=PTS-STARTPTS[video];"
        f"[0:a]atrim={0}:{end - start}ms,asetpts=PTS-STARTPTS[audio];"
    )
    cmd = [
        "-v",
        "quiet",
        "-ss",
        f"{start}ms",
        "-i",
        str(video),
        "-filter_complex",
        filter_command,
        "-map",
        "[video]",
        "-map",
        "[audio]",
        str(output),
    ]
    yield cmd


@ffmpeg()
def add_subs(video: Path, subs: Path, output: Path):
    # Then add the subs to the video
    yield [
        "-i",
        str(video),
        "-i",
        str(subs),
        "-c",
        "copy",
        "-disposition:s:0",
        "default",
        str(output),
    ]


def add_subs_from_string(video: Path, subs: str, output: Path):
    validate_video(video)
    with tempfile.TemporaryDirectory() as tempdir:
        subs_file = Path(tempdir) / "subs.ssa"
        subs_file.write_text(subs)

        add_subs(video, subs_file, output)


@ffmpeg()
def replace_subs(video, subs, output):
    # Then add the subs to the video
    yield [
        "-i",
        str(video),
        "-i",
        str(subs),
        "-map",
        "0:a",
        "-map",
        "0:v",
        "-map",
        "1",
        "-disposition:s:0",
        "default",
        "-c",
        "copy",
        str(output),
    ]


@attrs.frozen
class VideoPart:
    video: Path
    subs: str
    start: int
    end: int

    @property
    def duration_ms(self):
        return self.end - self.start

    @property
    def duration_us(self):
        return self.duration_ms * 1000


def supercut_free(video_parts: list[VideoPart], output: Path):
    with tempfile.TemporaryDirectory() as tempdir:
        temp = Path(tempdir)

        concat_list = []
        video_suffix = output.suffix
        with rich.progress.Progress() as progress:
            trim_task = progress.add_task(
                "Extracting video parts", total=len(video_parts)
            )
            for i, part in enumerate(video_parts):
                trimmed_video = temp / f"trim{i:04}{video_suffix}"
                trim_video(
                    video=part.video,
                    start=part.start,
                    end=part.end,
                    output=trimmed_video,
                )

                with_subs = temp / f"withsubs{i:04}{video_suffix}"
                add_subs_from_string(trimmed_video, part.subs, with_subs)
                concat_list.append(with_subs)
                progress.update(trim_task, advance=1)

        dirty_subs = temp / f"dirty{video_suffix}"
        total_out_time_us = sum(part.duration_us for part in video_parts)
        concat_videos.with_progress(
            total=Total(name=b"out_time_us", total=total_out_time_us, converter=int),
            description="Concatenating video parts",
        )(concat_list, dirty_subs)
        cleanup_subs(dirty_subs, output)


def cleanup_subs(video: Path, output: Path):
    subs = pysubs2.SSAFile.from_string(extract_subtitle_stream(video, 0).decode("utf8"))
    subs.events = sorted(subs.events, key=operator.attrgetter("start"))

    with tempfile.TemporaryDirectory() as tempdir:
        new_subs = Path(tempdir) / "new_subs.ssa"
        subs.save(str(new_subs))
        replace_subs(video, new_subs, output)


@ffmpeg()
def hardcode_subs(video: Path, output: Path):
    abs_video = video.absolute()
    abs_output = output.absolute()
    with contextlib.chdir(video.parent):
        yield ["-i", str(abs_video), "-vf", f"subtitles={video.name}", str(abs_output)]


def ffmpeg_progress(
    args: typing.Iterable[str],
    description: str = "",
    total: Total | None = None,
):
    progress_total = None
    if total is not None:
        progress_total = total.total

    with socket.socket() as server:
        server.bind(("localhost", 0))
        server.listen(1)
        host, port = server.getsockname()

        def run_ffmpeg():
            # We run in a thread, as we need to keep reading the output to avoid
            # blocking the pipe.
            subprocess.run(
                ["ffmpeg", "-progress", f"tcp://{host}:{port}", *args],
                capture_output=True,
            )

        try:
            ffmpeg_thread = threading.Thread(target=run_ffmpeg)
            ffmpeg_thread.start()
            conn, addr = server.accept()

            with conn:
                # We need to use `Progress` as a context manager here, and cannot use `rich.progress.track`.
                # Proper cleanup is critical in case of Ctrl-C, otherwise the program hangs.
                with rich.progress.Progress() as progress_bar:
                    task = progress_bar.add_task(
                        description=description, total=progress_total
                    )
                    for step_progress in recv_progress(conn):
                        if total is not None:
                            progress_bar.update(
                                task,
                                completed=total.converter(step_progress[total.name]),
                            )
                    progress_bar.update(task, total=100, completed=100)
        finally:
            ffmpeg_thread.join(1)


def recv_progress(conn: socket.socket) -> Iterator[dict]:
    for data in iter(lambda: conn.recv(1024), b""):
        yield parse_progress(data)


def parse_progress(progress: bytes) -> dict:
    raw_values = dict(line.split(b"=") for line in progress.splitlines())
    # There are more fields, but we ignore them.
    # It seems that `out_time_ms` yields th same values as `out_time_us`,
    # and both are microseconds and not milliseconds.
    return {key: value.strip() for key, value in raw_values.items()}


def ffmpeg_progress_iterator(
    args: typing.Iterable[str],
    progress_key: bytes,
    progress_converter: typing.Callable[[bytes], _T],
) -> typing.Iterator[_T]:
    with socket.socket() as server:
        server.bind(("localhost", 0))
        server.listen(1)
        host, port = server.getsockname()

        def run_ffmpeg():
            # We run in a thread, as we need to keep reading the output to avoid
            # blocking the pipe.
            subprocess.run(
                ["ffmpeg", "-progress", f"tcp://{host}:{port}", *args],
                capture_output=True,
            )

        class _Sentinel:
            pass

        progress_queue: queue.SimpleQueue[_T | _Sentinel] = queue.SimpleQueue()

        def advance():
            conn, addr = server.accept()

            with conn:
                for step_progress in recv_progress(conn):
                    progress_queue.put(progress_converter(step_progress[progress_key]))
                progress_queue.put(_Sentinel())

        try:
            advance_thread = threading.Thread(target=advance)
            ffmpeg_thread = threading.Thread(target=run_ffmpeg)
            # Start waiting for a connection
            advance_thread.start()
            # Start ffmpeg
            ffmpeg_thread.start()

            while 1:
                progress_value = progress_queue.get()
                if isinstance(progress_value, _Sentinel):
                    break
                yield progress_value

        finally:
            ffmpeg_thread.join(1)
            advance_thread.join(1)
