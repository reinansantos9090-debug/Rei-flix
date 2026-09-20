"""Deterministic, conservative identification for local media file names."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v", ".ts", ".m2ts", ".flv", ".wmv"}
_TECHNICAL = re.compile(r"\b(?:2160p|1080p|720p|480p|bluray|web[- .]?dl|webrip|x26[45]|10bit|hevc|av1|aac|flac|dublado|dual audio|legendado)\b", re.I)
_SEASON = re.compile(r"(?:\bS|season[ ._-]*|temporada[ ._-]*|temp[ ._-]*|T)(\d{1,2})(?=\b|[ ._-]*E)", re.I)
_SXXEXX = re.compile(r"\bS(\d{1,2})[ ._-]*E(?:P(?:ISODE)?)?[ ._-]*(\d{1,4})(?:v\d+)?\b", re.I)
_X_EPISODE = re.compile(r"\b(\d{1,2})\s*[xX]\s*(\d{1,4})(?:v\d+)?\b")
_WORD_EPISODE = re.compile(r"\b(?:E(?:P(?:ISODE)?)?)[ ._-]*(\d{1,4})(?:v\d+)?\b", re.I)
_SPECIAL = re.compile(r"\b(OVA|OAD|ONA|SPECIALS?|SP|EXTRA)(?:\b|(?=\d))[ ._-]*(\d{1,4})?", re.I)
_MOVIE = re.compile(r"\b(?:MOVIE|FILM)\b", re.I)


@dataclass(frozen=True)
class ParsedEpisode:
    anime_title: str
    season: int | None
    episode: float | None
    display_title: str
    extension: str
    episode_type: str = "unknown"
    identification_source: str = "unknown"
    confidence: str = "low"
    absolute_number: int | None = None


def _parts(path: str, library_root: str | None) -> list[str]:
    if library_root:
        try:
            relative = os.path.relpath(path, library_root)
            items = [item for item in relative.replace("\\", "/").split("/")[:-1] if item and item != "." and item != ".."]
            if items:
                return items
        except ValueError:
            pass
    return [item for item in path.replace("\\", "/").split("/")[:-1] if item]


def _clean_title(value: str) -> str:
    value = re.sub(r"\[[^\]]*(?:1080p|720p|x26[45]|hevc|av1|aac|flac)[^\]]*\]", "", value, flags=re.I)
    value = re.sub(r"^\s*\[[^\]]+\]\s*", "", value)  # release group only
    value = _TECHNICAL.sub("", value)
    value = re.sub(r"[._]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" -_[]()")
    return value


def _folder_season(parts: list[str]) -> int | None:
    for part in reversed(parts):
        match = _SEASON.search(part)
        if match:
            return int(match.group(1))
    return None


def parse_video_path(path: str, library_root: str | None = None) -> ParsedEpisode:
    """Identify episode structure without fabricating an episode or season.

    Explicit file patterns outrank folder context; ambiguous numeric suffixes
    are accepted only when they are not years or technical tokens.
    """
    file_name = os.path.basename(path)
    stem, extension = os.path.splitext(file_name)
    folders = _parts(path, library_root)
    parent = folders[-1] if folders else os.path.basename(os.path.dirname(path))
    season = _folder_season(folders)
    episode = None
    absolute_number = None
    kind, source, confidence = "unknown", "unknown", "low"
    marker = None

    special = _SPECIAL.search(stem)
    if special:
        episode = float(special.group(2)) if special.group(2) else None
        marker_kind = special.group(1).casefold()
        kind = "special" if marker_kind in {"special", "specials", "sp"} else marker_kind
        source, confidence, marker = "special_marker", "high", special
    elif _MOVIE.search(stem):
        kind, source, confidence, marker = "movie", "movie_marker", "high", _MOVIE.search(stem)
    else:
        absolute_match = re.search(r"\b(?:ABS(?:OLUTE)?|ANIME[- ._]?EP)[ ._-]*(\d{1,4})\b", stem, re.I)
        if absolute_match:
            absolute_number = int(absolute_match.group(1))
        explicit = _SXXEXX.search(stem)
        cross = _X_EPISODE.search(stem)
        word = _WORD_EPISODE.search(stem)
        if explicit:
            season, episode, marker = int(explicit.group(1)), float(explicit.group(2)), explicit
            kind, source, confidence = "regular", "sxxexx", "high"
        elif cross:
            season, episode, marker = int(cross.group(1)), float(cross.group(2)), cross
            kind, source, confidence = "regular", "x_episode", "high"
        elif word:
            episode, marker = float(word.group(1)), word
            season = season or 1
            kind, source, confidence = "regular", "episode_marker", "high"
        else:
            candidates = [] if re.fullmatch(r"\s*\d{1,4}(?:v\d+)?\s*", stem) else list(re.finditer(r"(?<!\d)(\d{1,4})(?:v\d+)?\b", stem))
            if candidates:
                candidate = candidates[-1]
                value = int(candidate.group(1))
                # Four-digit calendar years and technical resolution never mean episode.
                if not (1900 <= value <= 2099 or f"{value}p".casefold() in stem.casefold()):
                    episode, marker = float(value), candidate
                    season = season or 1
                    kind, source, confidence = "regular", "numeric_suffix", "medium"

    title_source = stem[:marker.start()] if marker else stem
    title = _clean_title(title_source)
    if not title or re.fullmatch(r"(?:e|ep|episode)?\s*\d+", title, re.I):
        title = _clean_title(parent)
    if _SEASON.fullmatch(title) and len(folders) > 1:
        title = _clean_title(folders[-2])
    if not title:
        title = "Arquivo não identificado"
    return ParsedEpisode(title, season, episode, stem, extension.lower(), kind, source, confidence, absolute_number)
