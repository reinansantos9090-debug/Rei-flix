"""Assistente local de organização por similaridade, sem enviar arquivos a uma IA externa."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


class AnimeOrganizer:
    """Classifica candidatos AniList e só confirma automaticamente casos fortes."""
    AUTO_CONFIRM_SCORE = 0.86
    MINIMUM_SCORE = 0.48

    @classmethod
    def rank(cls, local_title: str, candidates: list[dict]) -> list[dict]:
        local = normalize(local_title)
        ranked = []
        for candidate in candidates:
            titles = (candidate.get("title") or {}).values()
            score = max((SequenceMatcher(None, local, normalize(title or "")).ratio() for title in titles), default=0)
            item = dict(candidate)
            item["match_score"] = round(score, 3)
            ranked.append(item)
        return sorted(ranked, key=lambda item: item["match_score"], reverse=True)

    @classmethod
    def choose(cls, local_title: str, candidates: list[dict]) -> tuple[dict | None, bool, list[dict]]:
        ranked = cls.rank(local_title, candidates)
        best = ranked[0] if ranked and ranked[0]["match_score"] >= cls.MINIMUM_SCORE else None
        is_confident = bool(best and best["match_score"] >= cls.AUTO_CONFIRM_SCORE)
        return best, is_confident, ranked
