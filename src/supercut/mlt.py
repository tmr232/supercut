from pathlib import Path
from typing import Iterator

import attrs

from supercut import ffmpeg


def indent(line: str) -> str:
    return "  " + line


@attrs.frozen
class Element:
    tag: str
    attributes: dict[str, str]
    children: list["Element"] | str|None = None

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


def write_mlt(parts: list[ffmpeg.VideoPart]) -> str:
    producers: dict[str, Element] = {}
    video_to_producer: dict[Path, str] = {}

    for part in parts:
        if part.video in video_to_producer:
            continue

        producer_id = f"producer{len(producers)}"
        producer = Element(
            tag="producer",
            attributes=dict(id=producer_id),
            children=[
                Element(
                    tag="property",
                    attributes=dict(name="resource"),
                    children=str(part.video),
                )
            ],
        )

        producers[producer_id] = producer
        video_to_producer[part.video] = producer_id

    main_bin_entries = [
        Element(tag="entry", attributes=dict(producer=producer_id))
        for producer_id in producers
    ]

    main_bin = Element(
        tag="playlist",
        attributes={"id": "main_bin"},
        children=[
            Element(tag="property", attributes={"name": "xml_retain"}, children="1"),
            *main_bin_entries,
        ],
    )

    background = Element(tag="playlist", attributes={"id": "background"})

    playlist_entries = []

    for part in parts:
        entry = Element(
            tag="entry",
            attributes={
                "producer": video_to_producer[part.video],
                "in": ms_to_timecode(part.start),
                "out": ms_to_timecode(part.end),
            },
        )
        playlist_entries.append(entry)

    playlist = Element(
        tag="playlist", attributes={"id": "playlist0"}, children=playlist_entries
    )

    tractor = Element(
        tag="tractor",
        attributes={
            "id": "tractor1",
            "title": "Supercut",
            "in": ms_to_timecode(0),
            "out": ms_to_timecode(sum(part.duration_ms for part in parts)),
        },
        children=[
            Element(tag="property", attributes={"name": "shotcut"}, children="1"),
            Element(
                tag="property",
                attributes={"name": "shotcut:projectAudioChannels"},
                children="2",
            ),
            Element(
                tag="property",
                attributes={"name": "shotcut:projectFolder"},
                children="1",
            ),
            Element(tag="track", attributes={"producer": "background"}),
            Element(tag="track", attributes={"producer": "playlist0"}),
        ],
    )

    mlt = Element(
        tag="mlt",
        attributes=dict(
            LC_NUMERIC="C",
            version="7.23.0",
            title="Supercut",
            producer="main_bin",
        ),
        children=[*producers.values(), main_bin, background, playlist, tractor],
    )

    return '<?xml version="1.0" standalone="no"?>\n' + "\n".join(mlt.to_xml())


def ms_to_timecode(time_ms: int) -> str:
    total_seconds = time_ms / 1000
    seconds = total_seconds % 60
    minutes = int((total_seconds // 60) % 60)
    hours = int(total_seconds // 3600)

    return f"{hours:02}:{minutes:02}:{seconds:06.3f}"
