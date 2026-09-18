"""Parsing defensivo de nomes de arquivos da biblioteca local."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v"}
_NOISE = re.compile(r"\b(1080p|720p|480p|bluray|web[- .]?dl|webrip|x26[45]|hevc|aac|dublado|dual audio|legendado)\b", re.I)


@dataclass(frozen=True)
class ParsedEpisode:
    anime_title: str
    season: int
    episode: float | None
    display_title: str


def parse_video_path(path: str, library_root: str | None = None) -> ParsedEpisode:
    """Extrai informações sem assumir um único padrão de nomes.

    O diretório mais próximo que não é marcador de temporada é preferido quando
    o arquivo contém somente ``E03``/``03``.
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    parent = os.path.basename(os.path.dirname(path))
    relative_parts = []
    if library_root:
        try:
            relative_parts = os.path.relpath(path, library_root).split(os.sep)[:-1]
        except ValueError:
            pass
    season_match = re.search(r"(?:\bS|season[ ._-]*)(\d{1,2})\b", stem, re.I)
    if not season_match:
        for part in reversed(relative_parts + [parent]):
            season_match = re.search(r"(?:\bS|season[ ._-]*)(\d{1,2})\b", part, re.I)
            if season_match:
                break
    season = int(season_match.group(1)) if season_match else 1
    episode_match = re.search(r"(?:\bE(?:P(?:ISODE)?)?[ ._-]*|[ ._-])(\d{1,4})(?:v\d+)?\b", stem, re.I)
    if not episode_match:
        # "One Piece 1100" and an isolated "001" are common local names.
        candidates = list(re.finditer(r"\b(\d{1,4})(?:v\d+)?\b", stem))
        episode_match = candidates[-1] if candidates else None
    episode = float(episode_match.group(1)) if episode_match else None
    title_source = stem
    if episode_match:
        title_source = title_source[:episode_match.start()].strip(" ._-[]()")
    title_source = re.sub(r"\bS\d{1,2}\b", "", title_source, flags=re.I)
    title_source = _NOISE.sub("", title_source)
    title_source = re.sub(r"[._]+", " ", title_source)
    title_source = re.sub(r"\s+", " ", title_source).strip(" -")
    if not title_source or re.fullmatch(r"(?:e|ep|episode)?\s*\d+", title_source, re.I):
        title_source = parent
    # A pasta Anime/S04/E03 deve resultar em Anime, não S04.
    if re.fullmatch(r"(?:s|season)\d+", title_source, re.I) and relative_parts:
        title_source = relative_parts[-2] if len(relative_parts) > 1 else parent
    return ParsedEpisode(title_source or "Anime não identificado", season, episode, stem)
