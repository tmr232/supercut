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
    # Note that we need a different `chain` producer for every instance
    # of the same video. This includes the main bin, and the playlist.
    chains:list[Element] = []
    playlist_entries = []
    main_bin_videos = set()
    main_bin_ids = []
    for i, part in enumerate(parts):
        chain_id = f'chain{i}'
        ids = [chain_id]
        if part.video not in main_bin_videos:
            main_bin_id = f'main_bin_chain{i}'
            ids.append(main_bin_id)
            main_bin_ids.append(main_bin_id)
            main_bin_videos.add(part.video)

        for id_ in ids:
            chain = Element(
                tag="chain",
                attributes=dict(id=id_),
                children=[
                    Element(
                        tag="property",
                        attributes=dict(name="resource"),
                        children=str(part.video),
                    )
                ],
            )
            chains.append(chain)

        entry = Element(
            tag="entry",
            attributes={
                "producer": chain_id,
                "in": ms_to_timecode(part.start),
                "out": ms_to_timecode(part.end),
            },
        )
        playlist_entries.append(entry)

    main_bin = Element(
        tag="playlist",
        attributes={"id": "main_bin"},
        children=[
            Element(tag="property", attributes={"name": "xml_retain"}, children="1"),
            *(
        Element(tag="entry", attributes=dict(producer=id_))
        for id_ in main_bin_ids
            ),
        ],
    )


    background = Element(tag="playlist", attributes={"id": "background"})


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
        children=[*chains, main_bin, background, playlist, tractor],
    )

    return '<?xml version="1.0" standalone="no"?>\n' + "\n".join(mlt.to_xml())


def ms_to_timecode(time_ms: int) -> str:
    total_seconds = time_ms / 1000
    seconds = total_seconds % 60
    minutes = int((total_seconds // 60) % 60)
    hours = int(total_seconds // 3600)

    return f"{hours:02}:{minutes:02}:{seconds:06.3f}"
