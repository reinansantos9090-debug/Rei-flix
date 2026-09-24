import concurrent.futures
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from core.artwork import (
    ArtworkEngine,
    STATUS_FAILED,
    STATUS_READY,
    STATUS_RETRY_WAIT,
)
from core.library_service import LibraryService
from core.library_store import LibraryStore


JPEG = b"\\xff\\xd8\\xff" + b"JFIF" + b"\\x00" * 24


class ArtworkEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LibraryStore(self.tmp.name)
        self.engine = ArtworkEngine(self.store)

    def tearDown(self):
        self.engine.shutdown()
        self.tmp.cleanup()

    def _media(self, title="Ação 進撃", media_kind="series"):
        return self.store.upsert_anime("local", {"title": title, "genres": "[]", "media_kind": media_kind})

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

    def _remote(self, anime, url="https://example/cover.jpg", artwork_type="poster"):
        self.engine.sync_anime_metadata(
            anime,
            {"anilist_id": 16498, "cover_url": url, "banner_url": "https://example/banner.jpg"}
            if artwork_type == "poster"
            else {"cover_url": url},
        )

    def test_schema_and_persistence(self):
        self.assertEqual(self.store.SCHEMA_VERSION, 29)
        anime = self._media()
        path = Path(self.tmp.name) / "poster.jpg"
        path.write_bytes(JPEG)
        self.assertTrue(self.engine.add_local("anime", anime, "poster", path))
        reopened_store = LibraryStore(self.tmp.name)
        reopened = ArtworkEngine(reopened_store)
        try:
            row = reopened.resolve("anime", anime, "poster", allow_network=False)
            self.assertEqual(row["local_path"], str(path))
        finally:
            reopened.shutdown()

    def test_types_and_fallbacks(self):
        anime = self._media()
        for kind in ("poster", "backdrop", "thumbnail", "season_poster", "episode_thumbnail"):
            self.assertIsNone(self.engine.resolve("anime", anime, kind, allow_network=False))
        path = Path(self.tmp.name) / "cover.webp"
        path.write_bytes(JPEG)
        self.engine.add_local("anime", anime, "poster", path)
        thumbnail = self.engine.resolve("anime", anime, "thumbnail", allow_network=False)
        self.assertTrue(thumbnail["fallback"])

    def test_manual_artwork_has_priority(self):
        anime = self._media()
        manual = Path(self.tmp.name) / "manual.jpg"
        remote = Path(self.tmp.name) / "remote.jpg"
        manual.write_bytes(JPEG)
        remote.write_bytes(JPEG)
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
        (folder / "poster.jpg").write_bytes(JPEG)
        (folder / "random-photo.jpg").write_bytes(JPEG)
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
        poster.write_bytes(JPEG)
        ep = self._episode(anime, str(video), video.name)
        self.engine.reindex_episode(ep)
        self.assertTrue(self.engine.resolve("anime", anime, "poster", allow_network=False)["local_path"].endswith("Poster.jpg"))

    def test_episode_and_season_artwork(self):
        anime = self._media()
        folder = Path(self.tmp.name) / "Show"
        folder.mkdir()
        video = folder / "Show S01E01.mkv"
        video.write_bytes(b"video")
        (folder / "thumbnail.jpg").write_bytes(JPEG)
        (folder / "season.jpg").write_bytes(JPEG)
        ep = self._episode(anime, str(video), video.name)
        self.engine.reindex_episode(ep)
        self.assertIsNotNone(self.engine.resolve("episode", ep, "episode_thumbnail", allow_network=False))
        self.assertIsNotNone(self.engine.resolve("season", f"{anime}:season:1", "season_poster", allow_network=False))

    def test_generated_native_thumbnail_persists(self):
        anime = self._media("Thumb")
        episode_path = str(Path(self.tmp.name) / "Thumb S01E01.mkv")
        ep = self._episode(anime, episode_path, "Thumb S01E01.mkv")
        thumb = Path(self.tmp.name) / "native.jpg"
        thumb.write_bytes(JPEG)
        self.assertTrue(self.engine.register_generated_thumbnail(episode_path, thumb, size=123, modified_at=456))
        episode_art = self.engine.resolve("episode", ep, "episode_thumbnail", allow_network=False)
        anime_art = self.engine.resolve("anime", anime, "poster", allow_network=False)
        self.assertEqual(episode_art["source"], "generated")
        self.assertEqual(anime_art["source"], "generated")

    def test_cache_and_anilist_external_reference(self):
        anime = self._media()
        cached = Path(self.tmp.name) / "cached.jpg"
        cached.write_bytes(JPEG)
        self.engine.sync_anime_metadata(
            anime,
            {"cover_cache": str(cached), "cover_url": "https://example/cover.jpg", "banner_url": "https://example/banner.jpg"},
        )
        row = self.engine.resolve("anime", anime, "poster", allow_network=False)
        self.assertEqual(row["source"], "cache")
        backdrop = self.engine.resolve("anime", anime, "backdrop", allow_network=False)
        self.assertTrue(backdrop["fallback"])

    def test_download_success_is_atomic_and_persistent(self):
        anime = self._media()
        self._remote(anime)
        calls = []
        def downloader(url):
            calls.append(url)
            return JPEG, "image/jpeg", 200
        self.engine._downloader = downloader
        result = self.engine.request("anime", anime, "poster", priority=100, blocking=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["status"], STATUS_READY)
        self.assertTrue(Path(result["local_path"]).is_file())
        self.assertEqual(Path(result["local_path"]).read_bytes(), JPEG)
        self.assertFalse(any(p.name.endswith(".tmp") for p in self.engine.cache_dir.iterdir()))
        self.assertEqual(self.store.anime_metadata("local")["cover_cache"], result["local_path"])

    def test_cache_hit_does_not_download(self):
        anime = self._media()
        self._remote(anime)
        path = Path(self.tmp.name) / "existing.jpg"
        path.write_bytes(JPEG)
        self.engine.sync_anime_metadata(anime, {"anilist_id": 16498, "cover_url": "https://example/cover.jpg", "cover_cache": str(path)})
        self.engine._downloader = lambda _url: (_ for _ in ()).throw(AssertionError("network"))
        result = self.engine.request("anime", anime, "poster", blocking=True)
        self.assertEqual(result["local_path"], str(path))

    def test_duplicate_requests_share_one_physical_download(self):
        anime = self._media()
        self._remote(anime)
        calls = []
        lock = threading.Lock()
        def downloader(url):
            with lock:
                calls.append(url)
            time.sleep(0.08)
            return JPEG, "image/jpeg", 200
        self.engine._downloader = downloader
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self.engine.request, "anime", anime, "poster", priority=100, blocking=True),
                pool.submit(self.engine.request, "anime", anime, "poster", priority=100, blocking=True),
            ]
            results = [future.result(timeout=3) for future in futures]
        self.assertEqual(len(calls), 1)
        self.assertEqual(results[0]["local_path"], results[1]["local_path"])

    def test_priority_is_recorded_and_prefetch_is_bounded(self):
        anime = self._media()
        self._remote(anime)
        futures = self.engine.prefetch(
            [{"entity_type": "anime", "entity_id": anime, "artwork_type": "poster", "priority": 500}] * 200
        )
        self.assertLessEqual(len(futures), 100)

    def test_corrupt_cache_is_repaired(self):
        anime = self._media()
        bad = Path(self.tmp.name) / "bad.jpg"
        bad.write_bytes(b"not an image")
        self.engine.sync_anime_metadata(anime, {"anilist_id": 16498, "cover_url": "https://example/cover.jpg", "cover_cache": str(bad)})
        self.engine._downloader = lambda _url: (JPEG, "image/jpeg", 200)
        result = self.engine.request("anime", anime, "poster", blocking=True, force=True)
        self.assertEqual(result["status"], STATUS_READY)
        self.assertEqual(Path(result["local_path"]).read_bytes(), JPEG)

    def test_retry_backoff_is_bounded(self):
        anime = self._media()
        self._remote(anime, "https://example/retry.jpg")
        calls = []
        def downloader(url):
            calls.append(url)
            raise TimeoutError("timeout")
        self.engine._downloader = downloader
        first = self.engine.request("anime", anime, "poster", blocking=True)
        self.assertIsNone(first)
        row = self.engine.list_for("anime", anime, "poster")[0]
        self.assertEqual(row["status"], STATUS_RETRY_WAIT)
        self.assertGreater(row["next_retry_at"], time.time())
        second = self.engine.request("anime", anime, "poster", blocking=True)
        self.assertEqual(second["status"], STATUS_RETRY_WAIT)
        self.assertEqual(len(calls), 1)

    def test_404_enters_failed_without_retry_loop(self):
        anime = self._media()
        self._remote(anime, "https://example/missing.jpg")
        def downloader(_url):
            raise __import__("urllib.error").error.HTTPError(_url, 404, "missing", {}, None)
        self.engine._downloader = downloader
        self.assertIsNone(self.engine.request("anime", anime, "poster", blocking=True))
        self.assertEqual(self.engine.get_status("anime", anime, "poster"), STATUS_FAILED)

    def test_manual_retry_ignores_cooldown(self):
        anime = self._media()
        self._remote(anime, "https://example/retry-manual.jpg")
        calls = []
        self.engine._downloader = lambda url: (calls.append(url) or (JPEG, "image/jpeg", 200))
        with self.store._conn() as con:
            con.execute("UPDATE artwork SET status=?,next_retry_at=? WHERE entity_id=?", (STATUS_RETRY_WAIT, time.time() + 3600, str(anime)))
        self.engine.retry("anime", anime, "poster", priority=500)
        time.sleep(0.1)
        self.assertEqual(len(calls), 1)

    def test_clear_and_cleanup_never_touch_videos(self):
        anime = self._media()
        video = Path(self.tmp.name) / "video.mkv"
        video.write_bytes(b"video")
        cached = self.engine.cache_dir / "managed.jpg"
        cached.write_bytes(JPEG)
        self.engine.sync_anime_metadata(anime, {"cover_cache": str(cached), "cover_url": "https://example/cover.jpg"})
        removed = self.engine.clear()
        self.assertGreaterEqual(removed, 0)
        self.assertTrue(video.exists())
        self.assertTrue(Path(self.store.db_path).exists())

    def test_offline_missing_artwork_never_raises(self):
        anime = self._media()
        self.assertIsNone(self.engine.resolve("anime", anime, "backdrop", allow_network=False))
        self.assertEqual(self.store.catalog(), [])

    def test_movie_uses_stable_entity(self):
        movie = self._media("Filme", "movie")
        path = Path(self.tmp.name) / "movie.jpg"
        path.write_bytes(JPEG)
        self.engine.add_local("movie", movie, "poster", path)
        self.assertEqual(self.engine.resolve("movie", movie, "poster", allow_network=False)["local_path"], str(path))

    def test_metadata_integration_uses_existing_engine(self):
        service = LibraryService(self.store)
        anime = self._media()
        metadata = {"cover_url": "https://example/a.jpg", "cover_cache": "", "banner_url": "", "anilist_id": 1}
        service.artwork.sync_anime_metadata(anime, metadata)
        self.assertIsNone(self.store.association("local"))
        self.assertEqual(
            self.engine.resolve("anime", anime, "poster", allow_network=True)["external_url"],
            "https://example/a.jpg",
        )


if __name__ == "__main__":
    unittest.main()
