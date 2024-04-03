from pathlib import Path

from supercut.ffmpeg import VideoPart



def format_time(time_ms:int)->str:
    subsecond = (time_ms % 1000) // 10
    total_seconds = time_ms // 1000
    seconds = total_seconds % 60
    minutes = (total_seconds // 60) % 60
    hours = (total_seconds // 3600)

    return f"{hours:02}:{minutes:02}:{seconds:02}:{subsecond:02}"


def write_edl(title:str, parts:list[VideoPart]):
    edl_lines = []

    title = f"TITLE: {title}"
    edl_lines.append(title)

    record_in_ms = 0
    for i, part in enumerate(parts):
        edl_lines.append("")

        timing = f"{format_time(part.start)} {format_time(part.end)} {format_time(record_in_ms)} {format_time(record_in_ms + part.duration_ms)}"

        video = f"{i:03} BL V C {timing}"
        audio = f"{i:03} AX A C {timing}"
        source = f"* FROM CLIP NAME: {part.video!s}"

        edl_lines.append(video)
        edl_lines.append(audio)
        edl_lines.append(source)

        record_in_ms += part.duration_ms

    return "\n".join(edl_lines)


