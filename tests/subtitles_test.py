from __future__ import annotations

from pathlib import Path

import attrs
import iso639


@attrs.frozen
class File:
    name: str


@attrs.frozen
class Dir:
    name: str
    contents: list[File | Dir]


SAME_NAME = [
    File("movie.mkv"),
    File("movie.srt"),
]

SUBS_DIR = [
    File("movie.mkv"),
    Dir(
        "Subs",
        [
            File("ara.srt"),
            File("Brazilian.por.srt"),
            File("bul.srt"),
            File("cze.srt"),
            File("dan.srt"),
            File("dut.srt"),
            File("English.srt"),
            File("est.srt"),
            File("fin.srt"),
            File("fre.srt"),
            File("ger.srt"),
            File("gre.srt"),
            File("heb.srt"),
            File("hun.srt"),
            File("ind.srt"),
            File("ita.srt"),
            File("kor.srt"),
            File("Latin American.spa.srt"),
            File("lav.srt"),
            File("lit.srt"),
            File("nor.srt"),
            File("pol.srt"),
            File("por.srt"),
            File("rus.srt"),
            File("SDH.eng.HI.srt"),
            File("Simplified.chi.srt"),
            File("slo.srt"),
            File("slv.srt"),
            File("spa.srt"),
            File("swe.srt"),
            File("tha.srt"),
            File("Traditional.chi.srt"),
            File("tur.srt"),
        ],
    ),
]

def language_from_filename(filename:str)->tuple[iso639.Language, str|None]:
    match filename.split("."):
        case language, "srt":
            return iso639.Language.match(language), None
        case variant, language, "srt":
            return iso639.Language.match(language), variant

        case variant, language, _, "srt":
            return iso639.Language.match(language), variant

    raise ValueError(f"Filename does not represent a language: {filename}")

def choose_subs(filenames:list[str], language:str, variant:str|None=None)->str|None:
    desired_language = iso639.Language.match(language)

    best_candidate = None
    for filename in filenames:
        found_language, found_variant = language_from_filename(filename)

        if found_language == desired_language:
            if found_variant == variant:
                return filename

            # We have no real ranking. Only that a matching variant is better.
            best_candidate = filename

    return best_candidate