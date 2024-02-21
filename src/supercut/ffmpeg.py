import json
import operator
import subprocess
import tempfile
from pathlib import Path

import attrs
import pysubs2  # type: ignore[import-untyped]


def ensure_ffmpeg() -> bool:
    try:
        subprocess.check_call(["ffmpeg", "-version"], stdout=subprocess.PIPE)
        subprocess.check_call(["ffprobe", "-version"], stdout=subprocess.PIPE)
        return True
    except Exception:
        return False


def get_subtitle_stream_id(video: Path, language: str = "eng") -> int:
    """
    The subtitle stream index among subtitle streams.
    This ignores non-subtitle streams.
    """
    # First, probe the file to get the right stream
    probe_text = subprocess.check_output(
        ["ffprobe", "-print_format", "json", str(video), "-show_streams", "-v", "error"]
    )
    probe = json.loads(probe_text)

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


def concat_videos(videos: list[Path], output: Path):
    concat_list = (f"file '{video.absolute()!s}'" for video in videos)
    concat_text = "\n".join(concat_list)

    with tempfile.TemporaryDirectory() as tempdir:
        list_path = Path(tempdir) / "list.txt"
        list_path.write_text(concat_text)
        subprocess.check_call(
            [
                "ffmpeg",
                "-safe",
                "0",
                "-f",
                "concat",
                "-i",
                str(list_path),
                str(output),
            ]
        )


def validate_video(video: Path):
    subprocess.check_call(["ffprobe", str(video)])


def trim_video(video: Path, start: int, end: int, output: Path):
    filter_command = (
        f"[0:v]trim={0}:{end - start}ms,setpts=PTS-STARTPTS[video];"
        f"[0:a]atrim={0}:{end - start}ms,asetpts=PTS-STARTPTS[audio];"
    )
    cmd = [
        "ffmpeg",
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
    subprocess.check_call(cmd)


def add_subs(video: Path, subs: Path, output: Path):
    # Then add the subs to the video
    subprocess.check_call(
        [
            "ffmpeg",
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
    )


def add_subs_from_string(video: Path, subs: str, output: Path):
    subprocess.call(["ffprobe", str(video)])
    with tempfile.TemporaryDirectory() as tempdir:
        subs_file = Path(tempdir) / "subs.ssa"
        subs_file.write_text(subs)

        add_subs(video, subs_file, output)


def replace_subs(video, subs, output):
    # Then add the subs to the video
    subprocess.check_call(
        [
            "ffmpeg",
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
    )


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
