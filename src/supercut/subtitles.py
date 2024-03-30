from pathlib import Path

import pysubs2  # type: ignore[import-untyped]


def _is_sdh(subs: Path) -> bool:
    return "[SDH]" in str(subs)


def _find_in_subs_dir(video: Path, language: str) -> Path | None:
    subs_dir = video.parent / "Subs"
    if not subs_dir.is_dir():
        return None

    # Use sorting to prefer non-SDH subs
    return next(
        iter(
            sorted(
                subs_dir.glob(f"*.{language}.srt"),
                # For some reason, mypy thinks we can get a `None` value from the glob.
                key=_is_sdh,  # type: ignore[arg-type]
                reverse=True,
            )
        ),
        None,
    )


def find_srt_subs_for(video: Path, language: str = "eng") -> Path | None:
    if from_subs_dir := _find_in_subs_dir(video, language=language):
        return from_subs_dir

    if (in_same_dir := video.with_suffix(".srt")).is_file():
        return in_same_dir

    return None


def get_external_subs(video: Path, language: str = "eng") -> pysubs2.SSAFile:
    subs_path = find_srt_subs_for(video, language=language)
    if not subs_path:
        raise RuntimeError(f"Failed to find subs for {video}")

    subs = pysubs2.load(str(subs_path))
    # Use 16 as font size because that's the default size for ffmpeg.
    # As a result, when ffmpeg converts the subs back to .srt
    # later it won't add a `<font>` tag to them.
    subs.styles["Default"].fontsize = 16
    return subs
