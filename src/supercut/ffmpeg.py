import contextlib
import functools
import json
import operator
import socket
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Iterator

import attrs
import pysubs2  # type: ignore[import-untyped]
import rich.progress


def ensure_ffmpeg() -> bool:
    try:
        subprocess.check_call(["ffmpeg", "-version"], stdout=subprocess.PIPE)
        subprocess.check_call(["ffprobe", "-version"], stdout=subprocess.PIPE)
        return True
    except Exception:
        return False


def ffmpeg(description: str | None = None):
    def decorator(f):
        context_manager = contextlib.contextmanager(f)

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            print(f"Running {f.__name__}")
            with context_manager(*args, **kwargs) as args:
                ffmpeg_progress(args, description=description)

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


def supercut_free(video_parts: list[VideoPart], output: Path):
    with tempfile.TemporaryDirectory() as tempdir:
        temp = Path(tempdir)

        concat_list = []
        video_suffix = output.suffix
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

        dirty_subs = temp / f"dirty{video_suffix}"
        concat_videos(concat_list, dirty_subs)
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


def ffmpeg_progress(args: list[str], description: str | None = None):
    with socket.socket() as server:
        server.bind(("localhost", 0))
        server.listen(1)
        host, port = server.getsockname()

        def run_ffmpeg():
            # We run in a thread, as we need to keep reading the output to avoid
            # blocking the pipe.
            subprocess.run(
                ["ffmpeg", "-progress", f"tcp://{host}:{port}"] + args,
                capture_output=True,
            )

        try:
            ffmpeg_thread = threading.Thread(target=run_ffmpeg)
            ffmpeg_thread.start()
            conn, addr = server.accept()

            with conn:
                columns = [
                    rich.progress.TextColumn(
                        "[progress.description]{task.description}"
                    ),
                    rich.progress.BarColumn(),
                    rich.progress.TimeElapsedColumn(),
                ]
                # We need to use `Progress` as a context manager here, and cannot use `rich.progress.track`.
                # Proper cleanup is critical in case of Ctrl-C, otherwise the program hangs.
                with rich.progress.Progress(*columns) as progress:
                    task = progress.add_task(description=description, total=None)
                    for _ in recv_progress(conn):
                        pass
                    progress.update(task, total=100, completed=100)
        finally:
            ffmpeg_thread.join(1)


def recv_progress(conn: socket) -> Iterator[dict]:
    for data in iter(lambda: conn.recv(1024), b""):
        yield parse_progress(data)


def parse_progress(progress: bytes) -> dict:
    raw_values = dict(line.split(b"=") for line in progress.splitlines())
    # There are more fields, but we ignore them.
    # Also, it seems that `out_time_ms` yields th same values as `out_time_us`,
    # and both are microseconds and not milliseconds.
    return dict(
        # frame=int(raw_values[b"frame"].strip()),
        out_time_us=int(raw_values[b"out_time_us"].strip()),
        progress=raw_values[b"progress"].strip(),
    )
