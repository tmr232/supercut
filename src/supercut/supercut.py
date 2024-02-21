import io
import operator
import sys
import typing
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import attrs
import diskcache  # type: ignore[import-untyped]
import more_itertools
import pysubs2  # type: ignore[import-untyped]
import rich.console
import rich.table
import typer

from supercut import ffmpeg, vlc

app = typer.Typer(
    help="Subtitle-based automatic supercut generator",
    pretty_exceptions_show_locals=False,
)
edit_app = typer.Typer(
    help="Editable supercut generation", pretty_exceptions_show_locals=False
)
app.add_typer(edit_app, name="edit")


@attrs.define
class Core:
    _cache: diskcache.Cache

    @classmethod
    def from_dir(cls, cache_dir: Path | None) -> "Core":
        return Core(
            cache=diskcache.Cache(str(cache_dir) if cache_dir is not None else None)
        )

    def get_subs(self, video: Path, language: str) -> pysubs2.SSAFile:
        @self._cache.memoize(tag="raw_subs")
        def _get_raw_subs(video_, language_):
            return ffmpeg.extract_subs_by_language(
                video_, language=language_, fmt="ass"
            ).decode("utf8")

        return pysubs2.SSAFile.from_string(_get_raw_subs(video, language))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def get_sections(subs: pysubs2.SSAFile, query: str, *, name: str | None = None):
    events = query_events(subs, query, name=name)
    sections = [(e.start, e.end) for e in events]
    return sections


def query_events(subs: pysubs2.SSAFile, query: str, *, name: str | None = None):
    events = []
    lowered_query = query.lower()
    for event in subs.events:
        if name is not None and name.lower() != event.name.lower():
            continue
        if lowered_query in event.text.lower():
            events.append(event)
    return events


def copy_subs(subs: pysubs2.SSAFile) -> pysubs2.SSAFile:
    return pysubs2.SSAFile.from_string(subs.to_string("ass"))


def trim_subs(subs: pysubs2.SSAFile, start: int, end: int) -> pysubs2.SSAFile:
    """
    Notes:
        - If a video has subs that exceed its end, it will trail "nothing"
          when concatenated with other files.
    """
    subs = copy_subs(subs)

    def offset_event(event: pysubs2.SSAEvent, offset: int):
        event = event.copy()
        event.start += offset
        event.end += offset
        return event

    def is_in_range(event: pysubs2.SSAEvent, start: int, end: int):
        return event.start < end and event.end > start

    def squeeze_event(
        event: pysubs2.SSAEvent, start: int, end: int
    ) -> pysubs2.SSAEvent:
        event.start = max(event.start, start)
        event.end = min(event.end, end)
        return event

    subs.events = [
        squeeze_event(offset_event(event, -start), 0, start)
        for event in subs.events
        if is_in_range(event, start, end)
    ]

    return subs


@app.command()
def preview(
    videos: typing.Annotated[
        list[Path], typer.Argument(help="The videos to supercut, in order.")
    ],
    query: typing.Annotated[str, typer.Option(help="String to search in subtitles")],
    language: typing.Annotated[
        str, typer.Option(help="Subtitle language to use")
    ] = "eng",
    name: typing.Annotated[
        Optional[str], typer.Option(help="Name of the speaker.")
    ] = None,
    cache_dir: typing.Annotated[
        Optional[Path],
        typer.Option(help="Cache directory location. Speeds up repeated runs."),
    ] = None,
):
    """
    Quick preview using VLC
    """
    videos = sorted(videos)
    playlists = []
    with Core.from_dir(cache_dir) as core:
        with ThreadPoolExecutor() as executor:
            subs = executor.map(lambda video: core.get_subs(video, language), videos)
        for video, subs in zip(videos, subs):
            sections = get_sections(subs, query=query, name=name)
            playlist = vlc.create_supercut_playlist(video, sections)
            playlists.append(playlist)

        full_playlist = "\n".join(playlists)
        vlc.view_playlist(full_playlist)


@app.command()
def render(
    videos: typing.Annotated[
        list[Path], typer.Argument(help="The videos to supercut, in order.")
    ],
    query: typing.Annotated[str, typer.Option(help="String to search in subtitles")],
    output: typing.Annotated[Path, typer.Option(help="Ouptut file")],
    language: typing.Annotated[
        str, typer.Option(help="Subtitle language to use")
    ] = "eng",
    name: typing.Annotated[
        Optional[str], typer.Option(help="Name of the speaker.")
    ] = None,
    cache_dir: typing.Annotated[
        Optional[Path],
        typer.Option(help="Cache directory location. Speeds up repeated runs."),
    ] = None,
):
    """
    Render supercut
    """
    with Core.from_dir(cache_dir) as core:
        video_parts = []
        for video in videos:
            subs = core.get_subs(video, language)
            events = query_events(subs, query, name=name)
            for event in events:
                part = ffmpeg.VideoPart(
                    video=video,
                    subs=trim_subs(subs, event.start, event.end).to_string("ass"),
                    start=event.start,
                    end=event.end,
                )
                video_parts.append(part)

        ffmpeg.supercut_free(video_parts, output=output)


@app.command(name="list")
def list_subs(
    videos: typing.Annotated[
        list[Path], typer.Argument(help="The videos to supercut, in order.")
    ],
    query: typing.Annotated[str, typer.Option(help="String to search in subtitles")],
    language: typing.Annotated[
        str, typer.Option(help="Subtitle language to use")
    ] = "eng",
    name: typing.Annotated[
        Optional[str], typer.Option(help="Name of the speaker.")
    ] = None,
    cache_dir: typing.Annotated[
        Optional[Path],
        typer.Option(help="Cache directory location. Speeds up repeated runs."),
    ] = None,
):
    """Show all subs that match the query and name"""
    with Core.from_dir(cache_dir) as core:
        events = more_itertools.flatten(
            query_events(core.get_subs(video, language), query, name=name)
            for video in videos
        )

    for i, event in enumerate(events):
        text = event.plaintext.replace("\n", " ").replace("  ", " ")
        print(f"{i:-4} | {event.name}: {text}")


@app.command(name="names")
def list_names(
    videos: typing.Annotated[
        list[Path], typer.Argument(help="The videos to supercut, in order.")
    ],
    query: typing.Annotated[
        str, typer.Option(help="String to search in subtitles")
    ] = "",
    language: typing.Annotated[
        str, typer.Option(help="Subtitle language to use")
    ] = "eng",
    cache_dir: typing.Annotated[
        Optional[Path],
        typer.Option(help="Cache directory location. Speeds up repeated runs."),
    ] = None,
):
    """Show all speaker names in the subtitles"""
    names: defaultdict[str, int] = defaultdict(int)

    with Core.from_dir(cache_dir) as core:
        for video in videos:
            subs = core.get_subs(video, language)
            events = query_events(subs, query)
            for event in events:
                names[event.name] += 1

    print_names(names)


def print_names(names: dict[str, int]):
    table = rich.table.Table("Name", "Count")
    for name, count in sorted(
        names.items(), key=operator.itemgetter(1, 0), reverse=True
    ):
        table.add_row(name.capitalize(), str(count))

    console = rich.console.Console()
    console.print(table)


@edit_app.command(name="create")
def edit_create(
    videos: typing.Annotated[
        list[Path], typer.Argument(help="The videos to supercut, in order.")
    ],
    query: typing.Annotated[str, typer.Option(help="String to search in subtitles")],
    listfile: typing.Annotated[
        Optional[Path], typer.Option(help="List file to create; defaults to stdout")
    ] = None,
    language: typing.Annotated[
        str, typer.Option(help="Subtitle language to use")
    ] = "eng",
    name: typing.Annotated[
        Optional[str], typer.Option(help="Name of the speaker.")
    ] = None,
    cache_dir: typing.Annotated[
        Optional[Path],
        typer.Option(help="Cache directory location. Speeds up repeated runs."),
    ] = None,
):
    """
    Create edit list
    """

    with Core.from_dir(cache_dir) as core:
        events = more_itertools.flatten(
            query_events(core.get_subs(video, language), query, name=name)
            for video in videos
        )

    list_text = io.StringIO()
    for i, event in enumerate(events):
        text = event.plaintext.replace("\n", " ").replace("  ", " ")
        print(f"{i:-4} | {event.name}: {text}", file=list_text)

    if listfile is None:
        print(list_text.getvalue())
    else:
        listfile.write_text(list_text.getvalue())


def parse_list(listfile: Path) -> list[int]:
    indices = []
    for line in listfile.read_text().splitlines():
        if not line:
            continue
        if line.startswith("#"):
            continue
        indices.append(int(line.lstrip().partition(" ")[0]))

    return indices


@edit_app.command(name="preview")
def edit_preview(
    videos: typing.Annotated[
        list[Path], typer.Argument(help="The videos to supercut, in order.")
    ],
    query: typing.Annotated[str, typer.Option(help="String to search in subtitles")],
    listfile: typing.Annotated[Path, typer.Option(help="Edit list to load")],
    language: typing.Annotated[
        str, typer.Option(help="Subtitle language to use")
    ] = "eng",
    name: typing.Annotated[
        Optional[str], typer.Option(help="Name of the speaker.")
    ] = None,
    cache_dir: typing.Annotated[
        Optional[Path],
        typer.Option(help="Cache directory location. Speeds up repeated runs."),
    ] = None,
):
    """
    Preview supercut based on edit list
    """
    new_order = parse_list(listfile)

    playlist = []
    with Core.from_dir(cache_dir) as core:
        video_parts = []
        for video in videos:
            subs = core.get_subs(video, language)
            events = query_events(subs, query, name=name)
            for event in events:
                part = (video, event.start, event.end)
                video_parts.append(part)

        video_parts = [video_parts[i] for i in new_order]

        for video, start, stop in video_parts:
            playlist.append(f"#EXTVLCOPT:start-time={start/1000}")
            playlist.append(f"#EXTVLCOPT:stop-time={stop/1000}")
            if language:
                playlist.append(f"#EXTVLCOPT:sub-language={language}")
            playlist.append(str(video.absolute()))

        full_playlist = "\n".join(playlist)
        vlc.view_playlist(full_playlist)


@edit_app.command(name="render")
def edit_render(
    videos: typing.Annotated[
        list[Path], typer.Argument(help="The videos to supercut, in order.")
    ],
    query: typing.Annotated[str, typer.Option(help="String to search in subtitles")],
    listfile: typing.Annotated[Path, typer.Option(help="Edit list to load")],
    output: typing.Annotated[Path, typer.Option(help="Ouptut file")],
    language: typing.Annotated[
        str, typer.Option(help="Subtitle language to use")
    ] = "eng",
    name: typing.Annotated[
        Optional[str], typer.Option(help="Name of the speaker.")
    ] = None,
    cache_dir: typing.Annotated[
        Optional[Path],
        typer.Option(help="Cache directory location. Speeds up repeated runs."),
    ] = None,
):
    """
    Render supercut based on edit list.
    """
    new_order = parse_list(listfile)

    with Core.from_dir(cache_dir) as core:
        video_parts = []
        for video in videos:
            subs = core.get_subs(video, language)
            events = query_events(subs, query, name=name)
            for event in events:
                part = ffmpeg.VideoPart(
                    video=video,
                    subs=trim_subs(subs, event.start, event.end).to_string("ass"),
                    start=event.start,
                    end=event.end,
                )
                video_parts.append(part)

        video_parts = [video_parts[i] for i in new_order]

        ffmpeg.supercut_free(video_parts, output=output)


@app.command()
def check():
    """Ensure all requirements are met"""
    print("All good!")


@app.callback()
def callback():
    has_ffmpeg = ffmpeg.ensure_ffmpeg()
    has_vlc = vlc.ensure_vlc()

    if not has_ffmpeg:
        print(
            "Could not find ffmpeg or ffprobe in PATH. \nFor installation, see https://ffmpeg.org/",
            file=sys.stderr,
        )
    if not has_vlc:
        print(
            f"Could not find vlc in PATH or {vlc.VLC_ENV_VAR} variable.\nFor installation, see https://www.videolan.org/",
            file=sys.stderr,
        )

    if not has_vlc or not has_ffmpeg:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
