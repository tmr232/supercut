import contextlib
import os
import platform
import subprocess
import tempfile
from pathlib import Path
from typing import Iterator

import rich

WINDOWS_DEFAULT_PATH = r"C:\Program Files\VideoLAN\VLC\vlc.exe"

VLC_ENV_VAR = "SUPERCUT_VLC_PATH"


def get_vlc() -> str:
    if vlc := os.environ.get(VLC_ENV_VAR, None):
        return vlc

    if platform.system() == "Windows":
        if os.path.isfile(WINDOWS_DEFAULT_PATH):
            return WINDOWS_DEFAULT_PATH

    return "vlc"


def ensure_vlc() -> bool:
    try:
        subprocess.check_call([get_vlc(), "-I", "dummy", "vlc://quit"])
        return True
    except Exception:
        return False


def supercut(video: Path, sections: list[tuple[float, float]]):
    cuts = []
    for start, end in sections:
        cuts.extend(
            [f":start-time={start}", f":stop-time={end}", str(video.absolute())]
        )
    cmd = [get_vlc(), "--fullscreen", "--no-osd", *cuts, "vlc://quit"]
    rich.print(cmd)
    subprocess.check_call(cmd)


def create_supercut_playlist(
    video: Path, sections: list[tuple[int, int]], language: str | None = None
) -> str:
    lines = []
    for start, stop in sections:
        lines.append(f"#EXTVLCOPT:start-time={start/1000}")
        lines.append(f"#EXTVLCOPT:stop-time={stop/1000}")
        if language:
            lines.append(f"#EXTVLCOPT:sub-language={language}")
        lines.append(str(video.absolute()))

    return "\n".join(lines)


def view_playlist(playlist: str):
    with tempfile.TemporaryDirectory() as tempdir:
        playlist_file = Path(tempdir) / "playlist.m3u8"
        playlist_file.write_text(playlist)

        subprocess.check_call(
            [get_vlc(), "--fullscreen", "--no-osd", str(playlist_file), "vlc://quit"]
        )


def supercut_playlist(
    video: Path,
    sections: list[tuple[int, int]],
    output: Path | None = None,
    language: str | None = None,
):
    playlist = create_supercut_playlist(video, sections, language=language)

    @contextlib.contextmanager
    def _output_path() -> Iterator[Path]:
        if output is not None:
            yield output

        else:
            with tempfile.TemporaryDirectory() as tempdir:
                yield Path(tempdir) / "playlist.m3u8"

    with _output_path() as output_path:
        output_path.write_text(playlist)
        subprocess.check_call(
            [get_vlc(), "--fullscreen", "--no-osd", str(output_path), "vlc://quit"]
        )
