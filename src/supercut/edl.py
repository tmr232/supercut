from supercut.ffmpeg import VideoPart


def format_time(time_ms: int) -> str:
    frame = round((time_ms % 1000) / 1000 * 23.98) + 1
    total_seconds = time_ms // 1000
    seconds = total_seconds % 60
    minutes = (total_seconds // 60) % 60
    hours = total_seconds // 3600

    return f"{hours:02}:{minutes:02}:{seconds:02}:{frame:02}"


def write_edl(title: str, parts: list[VideoPart]):
    edl_lines = []

    title = f"TITLE: {title}"
    edl_lines.append(title)

    record_in_ms = 0
    for i, part in enumerate(parts, start=1):
        edl_lines.append("")

        timing = f"{format_time(part.start)} {format_time(part.end)} {format_time(record_in_ms)} {format_time(record_in_ms + part.duration_ms)}"

        # Use only the AX tape as OpenShot ignores the BL tape.
        video = f"{i:03}  AX       V     C        {timing}"
        audio = f"{i:03}  AX       A     C        {timing}"
        source = f"* FROM CLIP NAME: {part.video!s}"

        edl_lines.append(video)
        edl_lines.append(audio)
        edl_lines.append(source)

        record_in_ms += part.duration_ms

    return "\n".join(edl_lines)
