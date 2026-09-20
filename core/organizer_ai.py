"""Assistente local de organização por similaridade, sem enviar arquivos a uma IA externa."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = value.lower().replace("&", " and ")
    # Ignore technical filename tokens when comparing a local title with AniList.
    value = re.sub(r"\b(?:s\d{1,2}|e\d{1,4}|ep(?:isode)?\s*\d{1,4}|\d{3,4}p|x264|x265|hevc|av1|web[- ]?dl|webrip|bluray|bdrip|aac|flac|10bit|8bit)\b", " ", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _title_values(candidate: dict) -> list[str]:
    title = candidate.get("title") or {}
    values = [title.get("english"), title.get("romaji"), title.get("native")]
    values.extend(candidate.get("synonyms") or [])
    return [str(value).strip() for value in values if str(value or "").strip()]


def _token_score(local: str, remote: str) -> float:
    if not local or not remote:
        return 0.0
    if local == remote:
        return 1.0
    if local in remote or remote in local:
        containment = min(len(local), len(remote)) / max(len(local), len(remote))
        return 0.78 + (0.18 * containment)
    local_tokens, remote_tokens = set(local.split()), set(remote.split())
    overlap = len(local_tokens & remote_tokens) / len(local_tokens | remote_tokens) if local_tokens and remote_tokens else 0.0
    return max(SequenceMatcher(None, local, remote).ratio(), overlap)


def _candidate_score(local: str, candidate: dict) -> float:
    return max((_token_score(local, normalize(title)) for title in _title_values(candidate)), default=0.0)


class AnimeOrganizer:
    """Classifica candidatos AniList e só confirma automaticamente casos fortes."""
    AUTO_CONFIRM_SCORE = 0.86
    MINIMUM_SCORE = 0.48

    @classmethod
    def rank(cls, local_title: str, candidates: list[dict]) -> list[dict]:
        local = normalize(local_title)
        ranked = []
        for candidate in candidates:
            score = _candidate_score(local, candidate)
            item = dict(candidate)
            item["match_score"] = round(score, 3)
            ranked.append(item)
        return sorted(ranked, key=lambda item: item["match_score"], reverse=True)

    @classmethod
    def choose(cls, local_title: str, candidates: list[dict]) -> tuple[dict | None, bool, list[dict]]:
        ranked = cls.rank(local_title, candidates)
        best = ranked[0] if ranked and ranked[0]["match_score"] >= cls.MINIMUM_SCORE else None
        second = ranked[1]["match_score"] if len(ranked) > 1 else 0.0
        is_confident = bool(
            best
            and best["match_score"] >= cls.AUTO_CONFIRM_SCORE
            and (len(ranked) == 1 or best["match_score"] - second >= 0.04)
        )
        return best, is_confident, ranked
