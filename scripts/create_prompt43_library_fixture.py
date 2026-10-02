#!/usr/bin/env python3
"""Create the deterministic SQLite fixture used by Prompt 43 Android tests."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from core.library_store import LibraryStore


OUTPUT = Path("android/app/src/androidTest/assets/prompt43_library.sqlite3")


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="reianix-prompt43-") as directory:
        store = LibraryStore(directory)
        anime_id = store.upsert_anime(
            "prompt43-fixture",
            {
                "title": "Prompt 43 Fixture",
                "romaji": "Prompt 43 Fixture",
                "english": "Prompt 43 Fixture",
                "native": "Prompt 43 Fixture",
                "aliases": "[]",
                "genres": "[]",
                "anilist_id": 16498,
                "metadata_source": "anilist",
                "metadata_status": "available",
                "metadata_confidence": "high",
                "media_kind": "series",
            },
            source="anilist",
            confidence="high",
            status="available",
        )
        for number in range(1, 6):
            path = f"content://prompt43/fixture/{number}"
            episode_id = store.upsert_episode(
                anime_id,
                path,
                f"Prompt 43 Fixture S01E{number:02d}.mkv",
                1,
                number,
                mime_type="video/mp4",
                file_size=1000 + number,
                modified_at=1000 + number,
                source_folder="prompt43-fixture-source",
                media_identity=f"prompt43:fixture:{number}",
                episode_type="regular",
                episode_title=f"Prompt 43 Episode {number:02d}",
                identification_source="sxxexx",
                identification_confidence="high",
            )
            if number == 1:
                assert store.save_progress(
                    path,
                    37,
                    100,
                    episode_id=episode_id,
                    event_created_at=1_000 + number,
                )
        with store._conn() as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM episodes WHERE anime_id=?",
                (anime_id,),
            ).fetchone()[0] == 5

        OUTPUT.unlink(missing_ok=True)
        shutil.copy2(store.db_path, OUTPUT)

    print(f"Created {OUTPUT} with 5 local episodes and EP01 at 37%.")


if __name__ == "__main__":
    main()
