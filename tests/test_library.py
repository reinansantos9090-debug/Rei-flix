import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core.library_parser import parse_video_path
from core.library_store import LibraryStore
from core.library_service import LibraryService
from core.organizer_ai import AnimeOrganizer

class ParserTests(unittest.TestCase):
    def test_common_names(self):
        self.assertEqual(parse_video_path('Naruto - 001.mkv').anime_title, 'Naruto')
        self.assertEqual(parse_video_path('Naruto Shippuden - 023.mp4').episode, 23)
        self.assertEqual(parse_video_path('One Piece 1100.mkv').episode, 1100)
        p=parse_video_path('/videos/Attack on Titan/S04/E03.mkv','/videos')
        self.assertEqual((p.anime_title,p.season,p.episode),('Attack on Titan',4,3))
        p=parse_video_path('Jujutsu Kaisen - S02E15.mkv')
        self.assertEqual((p.anime_title,p.season,p.episode),('Jujutsu Kaisen',2,15))
    def test_invalid_file_is_safe(self):
        p=parse_video_path('sem-padrao.mkv')
        self.assertEqual(p.episode, None)
    def test_organizer_requires_review_for_uncertain_match(self):
        candidates=[{'id':1,'title':{'romaji':'Naruto'}},{'id':2,'title':{'romaji':'Boruto'}}]
        selected, confident, ranked=AnimeOrganizer.choose('Naruto Shipuden',candidates)
        self.assertEqual(selected['id'],1)
        self.assertFalse(confident)
        self.assertGreater(ranked[0]['match_score'], ranked[1]['match_score'])

class StoreTests(unittest.TestCase):
    def test_library_persists_episode_and_missing_flag(self):
        with tempfile.TemporaryDirectory() as d:
            store=LibraryStore(d); anime=store.upsert_anime('naruto',{'title':'Naruto','genres':'[]'})
            store.upsert_episode(anime,'/tmp/naruto-001.mkv','naruto-001.mkv',1,1)
            self.assertEqual(len(store.catalog()[0]['seasons'][0]['episodes']),1)
            store.mark_missing([])
            self.assertEqual(store.catalog(),[])

    def test_unavailable_folder_does_not_mark_existing_episodes_missing(self):
        with tempfile.TemporaryDirectory() as d:
            store=LibraryStore(d); anime=store.upsert_anime('naruto',{'title':'Naruto','genres':'[]'})
            store.upsert_episode(anime,'/previous/Naruto - 001.mkv','Naruto - 001.mkv',1,1)
            store.add_folder('/missing-folder')
            result=LibraryService(store).scan()
            self.assertEqual(result.catalog[0]['main_title'], 'Naruto')
            self.assertTrue(result.errors)

    def test_saf_reference_is_not_converted_to_path(self):
        with tempfile.TemporaryDirectory() as d:
            store=LibraryStore(d); store.add_folder('content://com.android.providers.media.documents/tree/video%3A1',kind='saf')
            result=LibraryService(store).scan()
            self.assertEqual(result.videos, 0)
            self.assertIn('aguardando scanner Android', result.errors[0])
            self.assertEqual(store.folders()[0]['authorization'], 'granted')

    def test_anilist_failure_does_not_abort_scan(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'Anime'; root.mkdir(); (root/'Naruto - 001.mkv').write_bytes(b'')
            store=LibraryStore(str(Path(d)/'data')); store.add_folder(str(root)); service=LibraryService(store)
            with patch.object(service.anilist,'search',return_value=[]):
                result=service.scan()
            self.assertEqual(result.catalog[0]['main_title'],'Naruto')
            self.assertEqual((result.animes,result.episodes),(1,1))


class AndroidBridgeTests(unittest.TestCase):
    def test_native_saf_documents_are_persisted_as_uris(self):
        with tempfile.TemporaryDirectory() as d:
            store=LibraryStore(d); service=LibraryService(store)
            with patch.object(service.anilist, 'search', return_value=[]):
                catalog=service.ingest_documents('content://tree/anime', [{
                    'uri':'content://document/naruto-001', 'name':'Naruto - 001.mkv',
                    'mimeType':'video/x-matroska', 'size':1234, 'modifiedAt':99,
                }])
            self.assertEqual(catalog[0]['seasons'][0]['episodes'][0]['path'], 'content://document/naruto-001')
            with store._conn() as con:
                row=con.execute('SELECT mime_type,file_size,modified_at FROM episodes').fetchone()
            self.assertEqual(tuple(row), ('video/x-matroska', 1234, 99))

if __name__ == '__main__': unittest.main()
