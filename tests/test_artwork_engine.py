import os
import tempfile
import time
import unittest
from pathlib import Path

from core.artwork import ArtworkEngine
from core.library_service import LibraryService
from core.library_store import LibraryStore


class ArtworkEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LibraryStore(self.tmp.name)
        self.engine = ArtworkEngine(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def _media(self, title="Ação 進撃"):
        anime = self.store.upsert_anime("local", {"title": title, "genres": "[]"})
        return anime

    def _episode(self, anime, path, name, season=1, number=1, episode_type="regular"):
        with self.store._conn() as con:
            cur = con.execute(
                """INSERT INTO episodes(anime_id,path,file_name,season,number,mime_type,file_size,modified_at,
                                         source_folder,missing,media_identity,absolute_number,episode_type,episode_title)
                   VALUES(?,?,?,?,?,?,?,?,?,0,?,?,?,?)""",
                (anime, path, name, season, number, None, None, None, str(Path(path).parent),
                 None, None, episode_type, None),
            )
            return cur.lastrowid

    def test_schema_and_persistence(self):
        self.assertEqual(self.store.SCHEMA_VERSION, 28)
        anime = self._media()
        path = Path(self.tmp.name) / "poster.jpg"
        path.write_bytes(b"poster")
        self.assertTrue(self.engine.add_local("anime", anime, "poster", path))
        reopened = ArtworkEngine(LibraryStore(self.tmp.name))
        row = reopened.resolve("anime", anime, "poster", allow_network=False)
        self.assertEqual(row["local_path"], str(path))

    def test_types_and_single_effective_role(self):
        anime = self._media()
        for kind in ("poster", "backdrop", "thumbnail", "season_poster", "episode_thumbnail"):
            self.assertIsNone(self.engine.resolve("anime", anime, kind, allow_network=False))
        path = Path(self.tmp.name) / "cover.webp"
        path.write_bytes(b"x")
        self.engine.add_local("anime", anime, "poster", path)
        self.assertEqual(self.engine.resolve("anime", anime, "poster", allow_network=False)["local_path"], str(path))

    def test_manual_artwork_has_priority_and_survives_external_refresh(self):
        anime = self._media()
        manual = Path(self.tmp.name) / "manual.jpg"
        remote = Path(self.tmp.name) / "remote.jpg"
        manual.write_bytes(b"m")
        remote.write_bytes(b"r")
        self.engine.set_manual("anime", anime, "poster", path=manual)
        self.engine.add_local("anime", anime, "poster", remote)
        self.engine.sync_anime_metadata(anime, {"cover_cache": str(remote), "cover_url": "https://example/cover.jpg"})
        row = self.engine.resolve("anime", anime, "poster", allow_network=False)
        self.assertEqual(row["source"], "manual")
        self.assertEqual(row["local_path"], str(manual))

    def test_local_conservative_discovery(self):
        anime = self._media()
        folder = Path(self.tmp.name) / "Show"
        folder.mkdir()
        video = folder / "Show S01E01.mkv"
        video.write_bytes(b"video")
        (folder / "poster.jpg").write_bytes(b"poster")
        (folder / "random-photo.jpg").write_bytes(b"ignore")
        ep = self._episode(anime, str(video), video.name)
        self.engine.reindex_episode(ep)
        rows = self.engine.list_for("anime", anime, "poster")
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["local_path"].endswith("poster.jpg"))

    def test_unicode_filename_is_discoverable(self):
        anime = self._media("進撃の巨人")
        folder = Path(self.tmp.name) / "進撃"
        folder.mkdir()
        video = folder / "進撃の巨人 S01E01.mkv"
        video.write_bytes(b"video")
        poster = folder / "Poster.jpg"
        poster.write_bytes(b"poster")
        ep = self._episode(anime, str(video), video.name)
        self.engine.reindex_episode(ep)
        self.assertTrue(self.engine.resolve("anime", anime, "poster", allow_network=False)["local_path"].endswith("Poster.jpg"))

    def test_episode_and_season_artwork(self):
        anime = self._media()
        folder = Path(self.tmp.name) / "Show"
        folder.mkdir()
        video = folder / "Show S01E01.mkv"
        video.write_bytes(b"video")
        (folder / "thumbnail.jpg").write_bytes(b"thumb")
        (folder / "season.jpg").write_bytes(b"season")
        ep = self._episode(anime, str(video), video.name)
        self.engine.reindex_episode(ep)
        self.assertIsNotNone(self.engine.resolve("episode", ep, "episode_thumbnail", allow_network=False))
        self.assertIsNotNone(self.engine.resolve("season", f"{anime}:season:1", "season_poster", allow_network=False))

    def test_generated_native_thumbnail_persists_for_episode_and_anime(self):
        anime = self._media("Thumb")
        episode_path = str(Path(self.tmp.name) / "Thumb S01E01.mkv")
        ep = self._episode(anime, episode_path, "Thumb S01E01.mkv")
        thumb = Path(self.tmp.name) / "native.jpg"
        thumb.write_bytes(b"jpeg")
        self.assertTrue(self.engine.register_generated_thumbnail(
            episode_path, thumb, size=123, modified_at=456
        ))
        episode_art = self.engine.resolve("episode", ep, "episode_thumbnail", allow_network=False)
        anime_art = self.engine.resolve("anime", anime, "poster", allow_network=False)
        self.assertEqual(episode_art["source"], "generated")
        self.assertEqual(episode_art["local_path"], str(thumb))
        self.assertEqual(anime_art["source"], "generated")
        self.assertEqual(anime_art["local_path"], str(thumb))

    def test_cache_and_anilist_external_reference(self):
        anime = self._media()
        cached = Path(self.tmp.name) / "cached.jpg"
        cached.write_bytes(b"cached")
        self.engine.sync_anime_metadata(anime, {
            "cover_cache": str(cached),
            "cover_url": "https://example/cover.jpg",
            "banner_url": "https://example/banner.jpg",
        })
        row = self.engine.resolve("anime", anime, "poster", allow_network=False)
        self.assertEqual(row["source"], "cache")
        backdrop = self.engine.resolve("anime", anime, "backdrop", allow_network=False)
        self.assertTrue(backdrop["fallback"])
        self.assertEqual(backdrop["local_path"], str(cached))

    def test_download_failure_preserves_existing_artwork(self):
        anime = self._media()
        old = Path(self.tmp.name) / "old.jpg"
        old.write_bytes(b"old")
        self.engine.add_local("anime", anime, "poster", old)
        self.engine.sync_anime_metadata(anime, {"cover_url": "https://example/new.jpg"})
        self.engine.mark_download_failure("anime", anime, "poster", "https://example/new.jpg")
        row = self.engine.resolve("anime", anime, "poster", allow_network=False)
        self.assertEqual(row["local_path"], str(old))

    def test_offline_missing_artwork_never_raises(self):
        anime = self._media()
        self.assertIsNone(self.engine.resolve("anime", anime, "backdrop", allow_network=False))
        self.assertEqual(self.store.catalog(), [])

    def test_movie_and_specials_use_stable_entities(self):
        movie = self.store.upsert_anime("movie", {"title": "Filme", "genres": "[]", "media_kind": "movie"})
        special = self._episode(movie, "/movie-special.mkv", "special.mkv", 0, 1, "special")
        path = Path(self.tmp.name) / "movie.jpg"
        path.write_bytes(b"movie")
        self.engine.add_local("movie", movie, "poster", path)
        self.assertEqual(self.engine.resolve("movie", movie, "poster", allow_network=False)["local_path"], str(path))
        self.assertIsNone(self.engine.resolve("special", special, "poster", allow_network=False))

    def test_reindex_after_move_keeps_logical_artwork_association(self):
        anime = self._media("Movido 進撃")
        old_dir = Path(self.tmp.name) / "old"
        new_dir = Path(self.tmp.name) / "new"
        old_dir.mkdir()
        video = old_dir / "Movido S01E01.mkv"
        video.write_bytes(b"video")
        (old_dir / "poster.jpg").write_bytes(b"poster")
        ep = self._episode(anime, str(video), video.name)
        self.engine.reindex_episode(ep)
        old_art = self.engine.resolve("anime", anime, "poster", allow_network=False)
        self.assertTrue(old_art["local_path"].endswith("poster.jpg"))

        new_dir.mkdir()
        new_video = new_dir / video.name
        video.rename(new_video)
        (old_dir / "poster.jpg").rename(new_dir / "poster.jpg")
        with self.store._conn() as con:
            con.execute("UPDATE episodes SET path=?,relative_path=? WHERE id=?", (str(new_video), new_video.name, ep))
        self.engine.reindex_episode(ep)
        resolved = self.engine.resolve("anime", anime, "poster", allow_network=False)
        self.assertEqual(resolved["local_path"], str(new_dir / "poster.jpg"))
        self.assertEqual(self.store.anime_metadata("local")["title"], "Movido 進撃")

    def test_failure_is_retryable_and_idempotent(self):
        anime = self._media()
        url = "https://example/retry.jpg"
        self.engine.sync_anime_metadata(anime, {"cover_url": url})
        self.assertTrue(self.engine.mark_download_failure("anime", anime, "poster", url))
        self.assertEqual(len(self.engine.retryable("anime", anime, "poster")), 1)
        self.engine.sync_anime_metadata(anime, {"cover_url": url})
        self.assertEqual(len(self.engine.list_for("anime", anime, "poster")), 1)

    def test_metadata_integration_uses_existing_engine_association(self):
        service = LibraryService(self.store)
        anime = self._media()
        metadata = {"cover_url": "https://example/a.jpg", "cover_cache": "", "banner_url": ""}
        self.store.upsert_anime("local", metadata, source="anilist", confidence="high", status="available")
        service.artwork.sync_anime_metadata(anime, metadata)
        self.assertEqual(self.store.association("local"), None)
        self.assertEqual(self.engine.resolve("anime", anime, "poster", allow_network=True)["external_url"], "https://example/a.jpg")


if __name__ == "__main__":
    unittest.main()
