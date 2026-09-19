import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from core.anilist import AniListClient


def media_payload(anilist_id=1):
    return {
        "id": anilist_id,
        "title": {"english": "Attack on Titan", "romaji": "Shingeki no Kyojin", "native": "進撃の巨人"},
        "synonyms": ["AOT"],
        "description": "Synopsis",
        "coverImage": {"extraLarge": "https://img.example/cover.jpg", "large": "https://img.example/cover-small.jpg"},
        "bannerImage": "https://img.example/banner.jpg",
        "genres": ["Action", "Drama"],
        "seasonYear": 2013,
        "season": "SPRING",
        "status": "FINISHED",
        "episodes": 25,
        "duration": 24,
        "averageScore": 91,
        "studios": {"nodes": [{"name": "WIT Studio"}]},
    }


class AniListClientTests(unittest.TestCase):
    def test_request_returns_graphql_data(self):
        client = AniListClient("/tmp/cache")
        response = {"data": {"Media": {"id": 123}}}
        fake = type("Response", (), {
            "__enter__": lambda self: self,
            "__exit__": lambda self, *args: None,
            "read": lambda self: json.dumps(response).encode(),
        })()
        with patch("core.anilist.urllib.request.urlopen", return_value=fake):
            self.assertEqual(client._request("query", {"id": 123}), response["data"])

    def test_request_fails_safe_for_network_error(self):
        client = AniListClient("/tmp/cache")
        with patch("core.anilist.urllib.request.urlopen", side_effect=URLError("offline")):
            self.assertIsNone(client._request("query", {}))

    def test_request_fails_safe_for_graphql_error_and_malformed_json(self):
        client = AniListClient("/tmp/cache")
        graphql_error = {"errors": [{"message": "rate limited"}], "data": None}
        fake = type("Response", (), {
            "__enter__": lambda self: self,
            "__exit__": lambda self, *args: None,
            "read": lambda self: json.dumps(graphql_error).encode(),
        })()
        with patch("core.anilist.urllib.request.urlopen", return_value=fake):
            self.assertIsNone(client._request("query", {}))
        malformed = type("Response", (), {
            "__enter__": lambda self: self,
            "__exit__": lambda self, *args: None,
            "read": lambda self: b"not-json",
        })()
        with patch("core.anilist.urllib.request.urlopen", return_value=malformed):
            self.assertIsNone(client._request("query", {}))

    def test_metadata_maps_anilist_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            client = AniListClient(directory)
            with patch.object(client, "cache_cover", return_value=str(Path(directory) / "cover.jpg")):
                metadata = client.metadata_from_media("Local title", media_payload(99))
            self.assertEqual(metadata["anilist_id"], 99)
            self.assertEqual(metadata["title"], "Attack on Titan")
            self.assertEqual(metadata["romaji"], "Shingeki no Kyojin")
            self.assertEqual(json.loads(metadata["aliases"]), ["AOT"])
            self.assertEqual(json.loads(metadata["genres"]), ["Action", "Drama"])
            self.assertEqual(metadata["studio"], "WIT Studio")
            self.assertEqual(metadata["episodes_count"], 25)

    def test_metadata_with_chosen_id_does_not_crash_on_candidates_without_id(self):
        client = AniListClient("/tmp/cache")
        candidate = {"title": {"romaji": "Attack on Titan"}}
        with patch.object(client, "by_id", return_value=None), patch.object(client, "search", return_value=[candidate]):
            result = client.metadata("Attack on Titan", chosen_id=123)
        self.assertEqual(result["title"], "Attack on Titan")
        self.assertNotIn("anilist_id", result)

    def test_cover_cache_reuses_non_empty_file_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            client = AniListClient(directory)
            url = "https://img.example/cover.jpg"
            expected = Path(directory) / next(iter(Path(directory).iterdir()), "missing")
            name = __import__("hashlib").sha256(url.encode()).hexdigest() + ".jpg"
            expected = Path(directory) / name
            expected.write_bytes(b"cached")
            with patch("core.anilist.urllib.request.urlopen") as request:
                self.assertEqual(client.cache_cover(url), str(expected))
                request.assert_not_called()

    def test_cover_cache_rejects_empty_download_and_cleans_temp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            client = AniListClient(directory)
            fake = type("Response", (), {
                "__enter__": lambda self: self,
                "__exit__": lambda self, *args: None,
                "read": lambda self: b"",
            })()
            with patch("core.anilist.urllib.request.urlopen", return_value=fake):
                self.assertEqual(client.cache_cover("https://img.example/empty.jpg"), "")
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cover_cache_retries_after_previous_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            client = AniListClient(directory)
            url = "https://img.example/retry.jpg"
            fake = type("Response", (), {
                "__enter__": lambda self: self,
                "__exit__": lambda self, *args: None,
                "read": lambda self: b"cover-bytes",
            })()
            with patch("core.anilist.urllib.request.urlopen", return_value=fake):
                path = client.cache_cover(url)
            self.assertTrue(Path(path).is_file())
            self.assertEqual(Path(path).read_bytes(), b"cover-bytes")


if __name__ == "__main__":
    unittest.main()
