import io
import operator
import sys
import typing
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Optional

import attrs
import diskcache  # type: ignore[import-untyped]
import more_itertools
import pysubs2  # type: ignore[import-untyped]
import rich.console
import rich.progress
import rich.table
import typer

from supercut import ffmpeg, mlt, vlc
from supercut.subtitles import get_external_subs
from supercut.video_part import VideoPart

app = typer.Typer(
    help="Subtitle-based automatic supercut generator",
    pretty_exceptions_show_locals=False,
)
edit_app = typer.Typer(
    help="Editable supercut generation", pretty_exceptions_show_locals=False
)
app.add_typer(edit_app, name="edit")

util_app = typer.Typer(help="Utility commands", pretty_exceptions_show_locals=False)
app.add_typer(util_app, name="util")


@attrs.define
class Core:
    _cache: diskcache.Cache
    _external_subs: bool

    @classmethod
    def from_dir(cls, cache_dir: Path | None, external_subs: bool = False) -> "Core":
        return Core(
            cache=diskcache.Cache(str(cache_dir) if cache_dir is not None else None),
            external_subs=external_subs,
        )

    def get_subs(self, video: Path, language: str) -> pysubs2.SSAFile:
        if self._external_subs:
            return get_external_subs(video, language)

        @self._cache.memoize(tag="raw_subs")
        def _get_raw_subs(video_, language_):
            return ffmpeg.extract_subs_by_language(
                video_, language=language_, fmt="ass"
            ).decode("utf8")

        return pysubs2.SSAFile.from_string(_get_raw_subs(video, language))

    def __enter__(self):
        self._cache.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._cache.__exit__(None, None, None)
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
    return deepcopy(subs)


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
        squeeze_event(offset_event(event, -start), 0, end - start)
        for event in subs.events
        if is_in_range(event, start, end)
    ]

    return subs


def _make_video_parts(
    *,
    videos: list[Path],
    cache_dir: Path | None,
    external_subs: bool,
    language: str,
    name: str | None,
    query: str,
) -> list[VideoPart]:
    videos = sorted(videos)
    with Core.from_dir(cache_dir, external_subs=external_subs) as core:
        video_parts = []
        all_subs = get_all_subs(videos, core, language)
        for video, subs in zip(videos, all_subs):
            events = query_events(subs, query, name=name)
            for event in events:
                part = VideoPart(
                    video=video,
                    subs=trim_subs(subs, event.start, event.end).to_string("ass"),
                    start=event.start,
                    end=event.end,
                )
                video_parts.append(part)
    return video_parts


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
    external_subs: typing.Annotated[
        bool, typer.Option(help="Search for external subs.")
    ] = False,
):
    """
    Quick preview using VLC
    """
    video_parts = _make_video_parts(
        videos=videos,
        cache_dir=cache_dir,
        external_subs=external_subs,
        language=language,
        name=name,
        query=query,
    )

    vlc.preview(video_parts, language=language)


def get_all_subs(
    videos: list[Path], core: Core, language: str
) -> list[pysubs2.SSAFile]:
    subs = []
    with rich.progress.Progress() as progress:
        task = progress.add_task("Getting subtitles", total=len(videos))
        for video in videos:
            subs.append(core.get_subs(video, language))
            progress.advance(task)
    return list(subs)


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
    external_subs: typing.Annotated[
        bool, typer.Option(help="Search for external subs.")
    ] = False,
):
    """
    Render supercut
    """
    video_parts = _make_video_parts(
        videos=videos,
        cache_dir=cache_dir,
        external_subs=external_subs,
        language=language,
        name=name,
        query=query,
    )

    ffmpeg.supercut_free(video_parts, output=output)


@app.command()
def export_mlt(
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
    external_subs: typing.Annotated[
        bool, typer.Option(help="Search for external subs.")
    ] = False,
):
    """
    Generate a ShotCut .mlt project of the supercut.
    """
    video_parts = _make_video_parts(
        videos=videos,
        cache_dir=cache_dir,
        external_subs=external_subs,
        language=language,
        name=name,
        query=query,
    )

    output.write_text(mlt.write_mlt(video_parts))


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
    external_subs: typing.Annotated[
        bool, typer.Option(help="Search for external subs.")
    ] = False,
):
    """Show all subs that match the query and name"""
    videos = sorted(videos)
    with Core.from_dir(cache_dir, external_subs=external_subs) as core:
        all_subs = get_all_subs(videos, core, language)
        events = more_itertools.flatten(
            query_events(subs, query, name=name) for subs in all_subs
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
    external_subs: typing.Annotated[
        bool, typer.Option(help="Search for external subs.")
    ] = False,
):
    """Show all speaker names in the subtitles"""
    names: defaultdict[str, int] = defaultdict(int)

    with Core.from_dir(cache_dir, external_subs=external_subs) as core:
        all_subs = get_all_subs(videos, core, language)
        for subs in all_subs:
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
    external_subs: typing.Annotated[
        bool, typer.Option(help="Search for external subs.")
    ] = False,
):
    """
    Create edit list
    """
    videos = sorted(videos)
    with Core.from_dir(cache_dir, external_subs=external_subs) as core:
        all_subs = get_all_subs(videos, core, language)
        events = more_itertools.flatten(
            query_events(subs, query, name=name) for subs in all_subs
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
        if line.lstrip().startswith("#"):
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
    external_subs: typing.Annotated[
        bool, typer.Option(help="Search for external subs.")
    ] = False,
):
    """
    Preview supercut based on edit list
    """
    new_order = parse_list(listfile)

    video_parts = _make_video_parts(
        videos=videos,
        cache_dir=cache_dir,
        external_subs=external_subs,
        language=language,
        name=name,
        query=query,
    )

    video_parts = [video_parts[i] for i in new_order]

    vlc.preview(video_parts, language=language)


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
    external_subs: typing.Annotated[
        bool, typer.Option(help="Search for external subs.")
    ] = False,
):
    """
    Render supercut based on edit list.
    """
    new_order = parse_list(listfile)

    video_parts = _make_video_parts(
        videos=videos,
        cache_dir=cache_dir,
        external_subs=external_subs,
        language=language,
        name=name,
        query=query,
    )

    video_parts = [video_parts[i] for i in new_order]

    ffmpeg.supercut_free(video_parts, output=output)


@util_app.command()
def hardcode_subs(
    video: typing.Annotated[Path, typer.Argument(help="The video to hardcode subs in")],
    output: typing.Annotated[Path, typer.Option(help="Ouptut file")],
):
    """Hardcode the subtitles into the video frames."""
    ffmpeg.hardcode_subs(video, output=output)


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
