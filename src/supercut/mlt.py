from pathlib import Path
from typing import Iterator

import attrs

from supercut import ffmpeg


def ms_to_timecode(time_ms: int) -> str:
    total_seconds = time_ms / 1000
    seconds = total_seconds % 60
    minutes = int((total_seconds // 60) % 60)
    hours = int(total_seconds // 3600)

    return f"{hours:02}:{minutes:02}:{seconds:06.3f}"


def indent(line: str) -> str:
    return "  " + line


@attrs.frozen
class Element:
    tag: str
    attributes: dict[str, str]
    children: list["Element"] | str | None = None

    def to_xml(self) -> Iterator[str]:
        attributes = " ".join(
            f'{name}="{value}"' for name, value in self.attributes.items()
        )

        if self.children is None:
            yield f"<{self.tag} {attributes}/>"

        elif isinstance(self.children, str):
            yield f"<{self.tag} {attributes}>{self.children}</{self.tag}>"

        else:
            yield f"<{self.tag} {attributes}>"

            for child in self.children:
                yield from map(indent, child.to_xml())

            yield f"</{self.tag}>"


def make_chain(*, id_: str, resource: Path) -> Element:
    return Element(
        tag="chain",
        attributes=dict(id=id_),
        children=[
            Element(
                tag="property",
                attributes=dict(name="resource"),
                children=str(resource),
            )
        ],
    )


def make_entry(*, producer_id: str, start: int, end: int) -> Element:
    return Element(
        tag="entry",
        attributes={
            "producer": producer_id,
            "in": ms_to_timecode(start),
            "out": ms_to_timecode(end),
        },
    )


def make_property(*, name: str, value: str) -> Element:
    return Element(
        tag="property",
        attributes={"name": name},
        children=value,
    )


def make_bin(parts: list[ffmpeg.VideoPart], bin_id: str) -> list[Element]:
    chains: list[Element] = []
    main_bin_ids = []
    for i, video in enumerate({part.video for part in parts}):
        main_bin_id = f"{bin_id}_chain{i}"
        main_bin_ids.append(main_bin_id)
        chains.append(make_chain(id_=main_bin_id, resource=video))

    main_bin = Element(
        tag="playlist",
        attributes={"id": bin_id},
        children=[
            make_property(name="xml_retain", value="1"),
            *(
                Element(tag="entry", attributes=dict(producer=id_))
                for id_ in main_bin_ids
            ),
        ],
    )
    return [*chains, main_bin]


def make_playlist(
    parts: list[ffmpeg.VideoPart], playlist_id: str, name: str | None = None
) -> list[Element]:
    chains: list[Element] = []
    playlist_entries = []
    for i, part in enumerate(parts):
        chain_id = f"{playlist_id}_chain{i}"
        chains.append(make_chain(id_=chain_id, resource=part.video))
        playlist_entries.append(
            make_entry(producer_id=chain_id, start=part.start, end=part.end)
        )

    if name is not None:
        playlist_entries.append(make_property(name="shotcut:name", value=name))

    playlist = Element(
        tag="playlist", attributes={"id": playlist_id}, children=playlist_entries
    )
    return [*chains, playlist]


def write_mlt(parts: list[ffmpeg.VideoPart]) -> str:
    main_bin_id = "main_bin"
    main_bin = make_bin(parts, main_bin_id)

    playlist_id = "playlist0"
    playlist = make_playlist(parts, playlist_id, name="Supercut")

    background = Element(tag="playlist", attributes={"id": "background"})

    tractor = Element(
        tag="tractor",
        attributes={
            "id": "tractor1",
            "title": "Supercut",
            "in": ms_to_timecode(0),
            "out": ms_to_timecode(sum(part.duration_ms for part in parts)),
        },
        children=[
            make_property(name="shotcut", value="1"),
            make_property(name="shotcut:projectAudioChannels", value="2"),
            make_property(name="shotcut:projectFolder", value="1"),
            Element(tag="track", attributes={"producer": "background"}),
            Element(tag="track", attributes={"producer": playlist_id}),
        ],
    )

    mlt = Element(
        tag="mlt",
        attributes=dict(
            LC_NUMERIC="C",
            version="7.23.0",
            title="Supercut",
            producer=main_bin_id,
        ),
        children=[*main_bin, background, *playlist, tractor],
    )

    return '<?xml version="1.0" standalone="no"?>\n' + "\n".join(mlt.to_xml())
