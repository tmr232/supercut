import itertools
import os
import platform
import subprocess
import tempfile
from pathlib import Path
from typing import Iterator

from supercut.video_part import VideoPart

WINDOWS_DEFAULT_PATH = r"C:\Program Files\VideoLAN\VLC\vlc.exe"

VLC_ENV_VAR = "SUPERCUT_VLC_PATH"


def get_vlc() -> str:
    if vlc := os.environ.get(VLC_ENV_VAR, None):
        return vlc

    if platform.system() == "Windows" and os.path.isfile(WINDOWS_DEFAULT_PATH):
        return WINDOWS_DEFAULT_PATH

    return "vlc"


def ensure_vlc() -> bool:
    try:
        subprocess.check_call([get_vlc(), "-I", "dummy", "vlc://quit"])
        return True
    except subprocess.CalledProcessError:
        return False


def _create_playlist_entry(part: VideoPart, language: str | None) -> Iterator[str]:
    yield f"#EXTVLCOPT:start-time={part.start / 1000}"
    yield f"#EXTVLCOPT:stop-time={part.end / 1000}"
    if language:
        yield f"#EXTVLCOPT:sub-language={language}"
    yield str(part.video.absolute())


def create_playlist(parts: list[VideoPart], language: str | None = None) -> str:
    return "\n".join(
        itertools.chain(
            *(_create_playlist_entry(part, language=language) for part in parts)
        )
    )


def view_playlist(playlist: str):
    with tempfile.TemporaryDirectory() as tempdir:
        playlist_file = Path(tempdir) / "playlist.m3u8"
        playlist_file.write_text(playlist)

        subprocess.check_call(
            [get_vlc(), "--fullscreen", "--no-osd", str(playlist_file), "vlc://quit"]
        )


def preview(parts: list[VideoPart], language: str | None = None):
    playlist = create_playlist(parts, language=language)
    view_playlist(playlist)
