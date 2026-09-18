import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core.library_parser import parse_video_path
from core.library_store import LibraryStore
from core.library_service import LibraryService
from core.organizer_ai import AnimeOrganizer, normalize
from views.home_view import HomeView
from views.organize_view import OrganizeView


def anilist_media(anilist_id=1, english='Jujutsu Kaisen', romaji=None, synonyms=None):
    return {
        'id': anilist_id,
        'title': {'english': english, 'romaji': romaji or english, 'native': None},
        'synonyms': synonyms or [], 'genres': ['Action'], 'seasonYear': 2020,
        'season': 'FALL', 'status': 'FINISHED', 'episodes': 24,
        'duration': 24, 'averageScore': 87, 'coverImage': {}, 'studios': {'nodes': []},
    }

class ParserTests(unittest.TestCase):
    def test_common_names(self):
        self.assertEqual(parse_video_path('Naruto - 001.mkv').anime_title, 'Naruto')
        self.assertEqual(parse_video_path('Naruto Shippuden - 023.mp4').episode, 23)
        self.assertEqual(parse_video_path('One Piece 1100.mkv').episode, 1100)
        p=parse_video_path('/videos/Attack on Titan/S04/E03.mkv','/videos')
        self.assertEqual((p.anime_title,p.season,p.episode),('Attack on Titan',4,3))
        p=parse_video_path('Jujutsu Kaisen - S02E15.mkv')
        self.assertEqual((p.anime_title,p.season,p.episode),('Jujutsu Kaisen',2,15))
        self.assertEqual(p.extension, '.mkv')
    def test_s01e01_and_episode_prefixes(self):
        s01 = parse_video_path('Frieren S01E01.mkv')
        ep = parse_video_path('Frieren EP01.mp4')
        long_ep = parse_video_path('Frieren Episode 01.webm')
        dashed = parse_video_path('Frieren - 01.m4v')
        self.assertEqual((s01.anime_title, s01.season, s01.episode), ('Frieren', 1, 1))
        self.assertEqual((ep.anime_title, ep.season, ep.episode), ('Frieren', 1, 1))
        self.assertEqual((long_ep.anime_title, long_ep.season, long_ep.episode), ('Frieren', 1, 1))
        self.assertEqual((dashed.anime_title, dashed.season, dashed.episode), ('Frieren', 1, 1))
    def test_invalid_file_is_safe(self):
        p=parse_video_path('sem-padrao.mkv')
        self.assertEqual(p.episode, None)
    def test_organizer_requires_review_for_uncertain_match(self):
        candidates=[{'id':1,'title':{'romaji':'Naruto'}},{'id':2,'title':{'romaji':'Boruto'}}]
        selected, confident, ranked=AnimeOrganizer.choose('Naruto Shipuden',candidates)
        self.assertEqual(selected['id'],1)
        self.assertFalse(confident)
        self.assertGreater(ranked[0]['match_score'], ranked[1]['match_score'])
    def test_normalize_and_alternative_title_match(self):
        candidate = anilist_media(16498, 'Attack on Titan', 'Shingeki no Kyojin', ['L Attaque des Titans'])
        self.assertEqual(normalize('Shingeki no Kyōjin!'), 'shingeki no kyojin')
        selected, confident, _ = AnimeOrganizer.choose('Shingeki no Kyojin', [candidate])
        self.assertEqual(selected['id'], 16498)
        self.assertTrue(confident)

class StoreTests(unittest.TestCase):
    def test_library_persists_episode_and_missing_flag(self):
        with tempfile.TemporaryDirectory() as d:
            store=LibraryStore(d); anime=store.upsert_anime('naruto',{'title':'Naruto','genres':'[]'})
            store.upsert_episode(anime,'/tmp/naruto-001.mkv','naruto-001.mkv',1,1,source_folder='/tmp')
            self.assertEqual(len(store.catalog()[0]['seasons'][0]['episodes']),1)
            store.mark_missing('/tmp', [])
            episode = store.catalog()[0]['seasons'][0]['episodes'][0]
            self.assertTrue(episode['missing'])

    def test_catalog_exposes_sqlite_playback_progress(self):
        with tempfile.TemporaryDirectory() as d:
            store = LibraryStore(d)
            anime = store.upsert_anime('naruto', {'title': 'Naruto', 'genres': '[]'})
            store.upsert_episode(anime, '/tmp/naruto-001.mkv', 'naruto-001.mkv', 1, 1)
            store.save_progress('/tmp/naruto-001.mkv', 95, 100)

            episode = store.catalog()[0]['seasons'][0]['episodes'][0]

            self.assertEqual(episode['progress'], 95)
            self.assertEqual(episode['duration'], 100)
            self.assertTrue(episode['watched'])

    def test_upsert_deduplicates_and_preserves_progress(self):
        with tempfile.TemporaryDirectory() as d:
            store = LibraryStore(d)
            anime = store.upsert_anime('naruto', {'title': 'Naruto', 'genres': '[]'})
            store.upsert_episode(anime, 'content://episode/1', 'Naruto - 001.mkv', 1, 1,
                                 'video/x-matroska', 100, 10, 'content://tree/one')
            store.save_progress('content://episode/1', 12, 24)
            store.upsert_episode(anime, 'content://episode/1', 'Naruto - 001.mkv', 1, 1,
                                 'video/x-matroska', 200, 20, 'content://tree/one')
            with store._conn() as con:
                row = con.execute('SELECT COUNT(*), progress, duration, file_size, modified_at FROM episodes').fetchone()
            self.assertEqual(tuple(row), (1, 12, 24, 200, 20))

    def test_missing_file_keeps_progress_and_is_recovered(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'Anime'; root.mkdir()
            video = root / 'Naruto - 001.mkv'; video.write_bytes(b'video')
            store = LibraryStore(str(Path(d) / 'data')); store.add_folder(str(root))
            service = LibraryService(store)
            with patch.object(service.anilist, 'search', return_value=[]):
                service.scan()
                store.save_progress(str(video), 30, 60)
                video.unlink(); service.scan()
                missing = store.catalog()[0]['seasons'][0]['episodes'][0]
                self.assertTrue(missing['missing'])
                self.assertEqual((missing['progress'], missing['duration']), (30, 60))
                video.write_bytes(b'video'); service.scan()
            recovered = store.catalog()[0]['seasons'][0]['episodes'][0]
            self.assertFalse(recovered['missing'])
            self.assertEqual((recovered['progress'], recovered['duration']), (30, 60))

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

    def test_multiple_folders_form_one_catalog_with_seasons(self):
        with tempfile.TemporaryDirectory() as d:
            first = Path(d) / 'Anime'; second = Path(d) / 'Downloads'
            first.mkdir(); second.mkdir()
            (first / 'Frieren S01E01.mkv').write_bytes(b'')
            (second / 'Frieren S02E01.mkv').write_bytes(b'')
            store = LibraryStore(str(Path(d) / 'data'))
            store.add_folder(str(first)); store.add_folder(str(second))
            service = LibraryService(store)
            with patch.object(service.anilist, 'search', return_value=[]):
                catalog = service.scan().catalog
            self.assertEqual(len(catalog), 1)
            self.assertEqual([season['season_name'] for season in catalog[0]['seasons']], ['Temporada 1', 'Temporada 2'])
            self.assertEqual(sum(len(season['episodes']) for season in catalog[0]['seasons']), 2)


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

    def test_saf_rescan_marks_only_missing_documents_from_its_tree(self):
        with tempfile.TemporaryDirectory() as d:
            store = LibraryStore(d); service = LibraryService(store)
            documents = [
                {'uri': 'content://document/one', 'name': 'Naruto - 001.mkv'},
                {'uri': 'content://document/two', 'name': 'Naruto - 002.mkv'},
            ]
            with patch.object(service.anilist, 'search', return_value=[]):
                service.ingest_documents('content://tree/anime', documents)
                store.save_progress('content://document/two', 10, 20)
                service.ingest_documents('content://tree/anime', documents[:1])
            episodes = store.catalog()[0]['seasons'][0]['episodes']
            self.assertFalse(episodes[0]['missing'])
            self.assertTrue(episodes[1]['missing'])
            self.assertEqual((episodes[1]['progress'], episodes[1]['duration']), (10, 20))

    def test_partial_saf_scan_does_not_mark_unread_documents_missing(self):
        with tempfile.TemporaryDirectory() as d:
            store = LibraryStore(d); service = LibraryService(store)
            document = {'uri': 'content://document/one', 'name': 'Naruto - 001.mkv'}
            with patch.object(service.anilist, 'search', return_value=[]):
                service.ingest_documents('content://tree/anime', [document])
                service.ingest_documents('content://tree/anime', [], scan_errors=['Sem acesso à subpasta'])
            episode = store.catalog()[0]['seasons'][0]['episodes'][0]
            self.assertFalse(episode['missing'])
            self.assertIn('Sem acesso', store.folders()[0]['last_error'])


class IdentificationTests(unittest.TestCase):
    def _service(self, directory):
        store = LibraryStore(directory)
        return store, LibraryService(store)

    def test_confident_result_is_cached_and_associated(self):
        with tempfile.TemporaryDirectory() as d:
            store, service = self._service(d)
            media = anilist_media(113415, 'Jujutsu Kaisen', synonyms=['Sorcery Fight'])
            with patch.object(service.anilist, 'search', return_value=[media]):
                metadata = service._identify('jujutsu kaisen', 'Jujutsu Kaisen', lambda _: None)
            store.upsert_anime('jujutsu kaisen', metadata)
            cached = store.anime_metadata('jujutsu kaisen')
            self.assertEqual(store.association('jujutsu kaisen'), 113415)
            self.assertEqual((cached['title'], cached['score']), ('Jujutsu Kaisen', 87))
            self.assertIn('Sorcery Fight', cached['aliases'])

    def test_fresh_cache_works_offline_without_searching_again(self):
        with tempfile.TemporaryDirectory() as d:
            store, service = self._service(d)
            media = anilist_media(1, 'Jujutsu Kaisen')
            with patch.object(service.anilist, 'search', return_value=[media]) as search:
                metadata = service._identify('jujutsu kaisen', 'Jujutsu Kaisen', lambda _: None)
                store.upsert_anime('jujutsu kaisen', metadata)
                cached = service._identify('jujutsu kaisen', 'Jujutsu Kaisen', lambda _: None)
            self.assertEqual(search.call_count, 1)
            self.assertEqual(cached['anilist_id'], 1)

    def test_manual_association_is_preserved_on_rescan(self):
        with tempfile.TemporaryDirectory() as d:
            store, service = self._service(d)
            store.resolve_match('jujutsu kaisen', 99)
            media = anilist_media(99, 'Jujutsu Kaisen')
            with patch.object(service.anilist, 'by_id', return_value=media) as by_id, \
                 patch.object(service.anilist, 'search') as search:
                metadata = service._identify('jujutsu kaisen', 'Jujutsu Kaisen', lambda _: None)
                store.upsert_anime('jujutsu kaisen', metadata)
                service._identify('jujutsu kaisen', 'Jujutsu Kaisen', lambda _: None)
            self.assertEqual(store.association('jujutsu kaisen'), 99)
            self.assertEqual(by_id.call_count, 1)
            search.assert_not_called()

    def test_ambiguous_and_empty_results_stay_unidentified(self):
        with tempfile.TemporaryDirectory() as d:
            store, service = self._service(d)
            candidates = [anilist_media(1, 'Naruto'), anilist_media(2, 'Boruto')]
            with patch.object(service.anilist, 'search', return_value=candidates):
                ambiguous = service._identify('naruto shipuden', 'Naruto Shipuden', lambda _: None)
            with patch.object(service.anilist, 'search', return_value=[]):
                missing = service._identify('arquivo local', 'Arquivo Local', lambda _: None)
            self.assertNotIn('anilist_id', ambiguous)
            self.assertEqual(store.pending_matches()[0]['lookup_title'], 'naruto shipuden')
            self.assertEqual(missing['title'], 'Arquivo Local')

    def test_rescan_keeps_local_seasons_and_does_not_repeat_metadata_request(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'Anime'; root.mkdir()
            (root / 'Jujutsu Kaisen S01E01.mkv').write_bytes(b'')
            (root / 'Jujutsu Kaisen S02E01.mkv').write_bytes(b'')
            store = LibraryStore(str(Path(d) / 'data')); store.add_folder(str(root))
            service = LibraryService(store); media = anilist_media(1, 'Jujutsu Kaisen')
            with patch.object(service.anilist, 'search', return_value=[media]) as search:
                first = service.scan().catalog
                second = service.scan().catalog
            self.assertEqual(search.call_count, 1)
            self.assertEqual([season['season_name'] for season in second[0]['seasons']], ['Temporada 1', 'Temporada 2'])
            self.assertEqual(sum(len(s['episodes']) for s in first[0]['seasons']), 2)


class LibraryStateTests(unittest.TestCase):
    def _episodes(self, store, title='One Piece'):
        anime = store.upsert_anime(title.casefold(), {'title': title, 'genres': '[]'})
        paths = []
        for season, number in ((1, 1), (1, 2), (1, 3), (2, 1)):
            path = f'/library/{title}-{season}-{number}.mkv'
            store.upsert_episode(anime, path, Path(path).name, season, number, source_folder='/library')
            paths.append(path)
        return anime, paths

    def test_add_remove_and_list_favorites_persist_after_reopen(self):
        with tempfile.TemporaryDirectory() as d:
            store = LibraryStore(d); anime, _ = self._episodes(store)
            self.assertTrue(store.toggle_favorite(anime))
            reopened = LibraryStore(d)
            self.assertTrue(reopened.is_favorite(anime))
            self.assertEqual([item['id'] for item in reopened.catalog(favorites_only=True)], [anime])
            self.assertFalse(reopened.toggle_favorite(anime))
            self.assertEqual(reopened.catalog(favorites_only=True), [])

    def test_progress_and_history_persist_after_reopen(self):
        with tempfile.TemporaryDirectory() as d:
            store = LibraryStore(d); _, paths = self._episodes(store)
            store.save_progress(paths[1], 30, 100)
            reopened = LibraryStore(d)
            current = reopened.current_episode(1)
            self.assertEqual((current['path'], current['progress'], current['duration']), (paths[1], 30, 100))
            self.assertIsNotNone(current['last_played_at'])
            history = reopened.playback_history()
            self.assertEqual((history[0]['anime_id'], history[0]['path'], history[0]['season']), (1, paths[1], 1))

    def test_continue_watching_orders_recent_and_skips_missing(self):
        with tempfile.TemporaryDirectory() as d:
            store = LibraryStore(d)
            first, first_paths = self._episodes(store, 'One Piece')
            second, second_paths = self._episodes(store, 'Jujutsu Kaisen')
            store.save_progress(first_paths[0], 20, 100)
            store.save_progress(second_paths[0], 40, 100)
            with store._conn() as con:
                con.execute('UPDATE episodes SET last_played_at=10 WHERE path=?', (first_paths[0],))
                con.execute('UPDATE episodes SET last_played_at=20 WHERE path=?', (second_paths[0],))
                con.execute('UPDATE episodes SET missing=1 WHERE path=?', (first_paths[0],))
            items = store.continue_watching()
            self.assertEqual([item['anime_id'] for item in items], [second])
            self.assertEqual(items[0]['path'], second_paths[0])

    def test_next_episode_crosses_season_and_skips_missing(self):
        with tempfile.TemporaryDirectory() as d:
            store = LibraryStore(d); _, paths = self._episodes(store)
            self.assertEqual(store.next_episode(paths[1])['path'], paths[2])
            with store._conn() as con:
                con.execute('UPDATE episodes SET missing=1 WHERE path=?', (paths[2],))
            self.assertEqual(store.next_episode(paths[1])['path'], paths[3])

    def test_previous_episode_crosses_season_and_skips_missing(self):
        with tempfile.TemporaryDirectory() as d:
            store = LibraryStore(d); _, paths = self._episodes(store)
            self.assertEqual(store.previous_episode(paths[2])['path'], paths[1])
            with store._conn() as con:
                con.execute('UPDATE episodes SET missing=1 WHERE path=?', (paths[1],))
            self.assertEqual(store.previous_episode(paths[2])['path'], paths[0])
            self.assertIsNone(store.previous_episode(paths[0]))

    def test_completed_episode_continues_with_next_available(self):
        with tempfile.TemporaryDirectory() as d:
            store = LibraryStore(d); anime, paths = self._episodes(store)
            store.save_progress(paths[1], 95, 100)
            current = store.current_episode(anime)
            self.assertEqual(current['path'], paths[2])
            continuation = store.continue_watching()
            self.assertEqual(continuation[0]['path'], paths[2])

    def test_rescan_preserves_favorite_progress_and_watched(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'Anime'; root.mkdir(); video = root / 'Naruto - 001.mkv'; video.write_bytes(b'')
            store = LibraryStore(str(Path(d) / 'data')); store.add_folder(str(root)); service = LibraryService(store)
            with patch.object(service.anilist, 'search', return_value=[]):
                first = service.scan().catalog[0]
                store.toggle_favorite(first['id'])
                store.save_progress(str(video), 95, 100)
                rescanned = service.scan().catalog[0]
            episode = rescanned['seasons'][0]['episodes'][0]
            self.assertTrue(rescanned['favorite'])
            self.assertEqual((episode['progress'], episode['duration']), (95, 100))
            self.assertTrue(episode['watched'])


class LibraryBrowseTests(unittest.TestCase):
    def _catalog(self):
        with tempfile.TemporaryDirectory() as d:
            store = LibraryStore(d)
            action = store.upsert_anime('attack', {'title': 'Attack on Titan', 'romaji': 'Shingeki no Kyojin', 'aliases': '["AoT"]', 'genres': '["Ação"]'})
            comedy = store.upsert_anime('nichijou', {'title': 'Nichijou', 'genres': '["Comédia"]'})
            store.upsert_episode(action, '/a1.mkv', 'Attack - 001.mkv', 1, 1, source_folder='/')
            store.upsert_episode(comedy, '/n1.mkv', 'Nichijou - 001.mkv', 1, 1, source_folder='/')
            store.toggle_favorite(action)
            store.save_progress('/a1.mkv', 40, 100)
            return store.catalog()

    def test_browse_catalog_filters_states_genre_and_local_aliases(self):
        catalog = self._catalog()
        self.assertEqual(len(LibraryService.browse_catalog(catalog)), 2)
        self.assertEqual(LibraryService.browse_catalog(catalog, state='Favoritos')[0]['main_title'], 'Attack on Titan')
        self.assertEqual(LibraryService.browse_catalog(catalog, state='Em andamento')[0]['main_title'], 'Attack on Titan')
        self.assertEqual(LibraryService.browse_catalog(catalog, genre='Comédia')[0]['main_title'], 'Nichijou')
        self.assertEqual(LibraryService.browse_catalog(catalog, query='shingeki')[0]['main_title'], 'Attack on Titan')
        self.assertEqual(LibraryService.browse_catalog(catalog, query='aot')[0]['main_title'], 'Attack on Titan')

    def test_browse_catalog_sorts_without_inventing_state(self):
        catalog = self._catalog()
        self.assertEqual([item['main_title'] for item in LibraryService.browse_catalog(catalog, sort='Nome A-Z')], ['Attack on Titan', 'Nichijou'])
        self.assertEqual([item['main_title'] for item in LibraryService.browse_catalog(catalog, sort='Nome Z-A')], ['Nichijou', 'Attack on Titan'])
        self.assertEqual(LibraryService.browse_catalog(catalog, state='Concluídos'), [])

    def test_home_builds_for_an_empty_local_catalog(self):
        class FakePage:
            def update(self): pass
            def run_thread(self, work): work()
        with tempfile.TemporaryDirectory() as d:
            view = HomeView.build(FakePage(), LibraryService(LibraryStore(d)), lambda _: None, lambda: None, lambda *args, **kwargs: None)
        self.assertEqual(view.content.controls[0].__class__.__name__, 'Row')


class DetailsDomainTests(unittest.TestCase):
    def _store_with_episodes(self, directory):
        store = LibraryStore(directory)
        anime = store.upsert_anime('details', {'title': 'Details', 'genres': '[]'})
        paths = []
        for season, number in ((1, 1), (1, 2), (2, 1)):
            path = f'/library/details-{season}-{number}.mkv'
            store.upsert_episode(anime, path, Path(path).name, season, number, source_folder='/library')
            paths.append(path)
        return store, anime, paths

    def test_playback_target_starts_first_available_and_returns_none_without_episodes(self):
        with tempfile.TemporaryDirectory() as d:
            store = LibraryStore(d)
            empty = store.upsert_anime('empty', {'title': 'Empty', 'genres': '[]'})
            self.assertIsNone(store.playback_target(empty))
            store, anime, paths = self._store_with_episodes(d)
            self.assertEqual(store.playback_target(anime)['path'], paths[0])

    def test_playback_target_prefers_partial_then_next_available_after_completion(self):
        with tempfile.TemporaryDirectory() as d:
            store, anime, paths = self._store_with_episodes(d)
            store.save_progress(paths[1], 20, 100)
            self.assertEqual(store.playback_target(anime)['path'], paths[1])
            store.save_progress(paths[1], 95, 100)
            self.assertEqual(store.playback_target(anime)['path'], paths[2])
            with store._conn() as con:
                con.execute('UPDATE episodes SET missing=1 WHERE path=?', (paths[2],))
            self.assertEqual(store.playback_target(anime)['path'], paths[0])

    def test_catalog_details_fields_keep_local_and_anilist_counts_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            store = LibraryStore(d)
            anime = store.upsert_anime('metadata', {
                'title': 'Metadata', 'genres': '["Drama"]', 'episodes_count': 12,
                'year': 2024, 'score': 84, 'status': 'RELEASING',
            })
            store.upsert_episode(anime, '/library/metadata-1.mkv', 'Metadata - 01.mkv', 1, 1)
            catalog = store.catalog()[0]
            self.assertEqual(catalog['meta']['episodes_count'], 12)
            self.assertEqual(len(catalog['seasons'][0]['episodes']), 1)
            self.assertEqual(catalog['seasons'][0]['episodes'][0]['number'], 1)
            self.assertEqual(catalog['seasons'][0]['season'], 1)


class DetailsViewTests(unittest.TestCase):
    class FakePage:
        def __init__(self):
            self.updates = 0
            self.snack_bar = None
        def update(self):
            self.updates += 1

    def _build(self, anime, target=None):
        from views.details_view import DetailView
        played = []
        page = self.FakePage()
        view = DetailView.build(
            page, anime,
            lambda path, title, **kwargs: played.append((path, title, kwargs)),
            lambda: None, lambda _: True, lambda _: target,
        )
        return page, view, played

    def test_builds_for_anime_without_metadata_or_episodes(self):
        _, view, _ = self._build({'id': 1, 'main_title': 'Arquivo local', 'meta': {}, 'seasons': []})
        self.assertEqual(view.content.controls[0].__class__.__name__, 'Row')
        self.assertIn('Nenhum episódio', view.content.controls[-1].controls[0].content.value)

    def test_builds_complete_metadata_and_uses_local_episode_uri(self):
        episode = {'path': 'content://document/episode-1', 'title': 'Anime - 01.mkv', 'season': 1,
                   'number': 1, 'progress': 30, 'duration': 100, 'watched': False, 'missing': False}
        anime = {
            'id': 2, 'main_title': 'Anime', 'favorite': False, 'genres': ['Ação'],
            'meta': {'title': 'Anime', 'english': 'Anime English', 'year': 2024, 'status': 'RELEASING',
                     'episodes_count': 12, 'score': 84, 'description': 'Descrição local em cache.'},
            'current_episode': episode, 'seasons': [{'season_name': 'Temporada 1', 'season': 1, 'episodes': [episode]}],
        }
        _, view, played = self._build(anime, episode)
        def walk(control):
            yield control
            for child in getattr(control, 'controls', []) or []:
                yield from walk(child)
            content = getattr(control, 'content', None)
            if content is not None:
                yield from walk(content)

        primary = next(item for item in walk(view) if item.__class__.__name__ == 'FilledButton')
        primary.on_click(None)
        self.assertEqual(played[0][0], 'content://document/episode-1')
        self.assertEqual(played[0][2]['progress_seconds'], 30)
        self.assertEqual(anime['meta']['episodes_count'], 12)
        self.assertEqual(len(anime['seasons'][0]['episodes']), 1)

    def test_missing_episode_is_not_clickable(self):
        missing = {'path': '/library/missing.mkv', 'title': 'Missing', 'season': 1, 'number': 1,
                   'progress': 20, 'duration': 100, 'watched': False, 'missing': True}
        anime = {'id': 3, 'main_title': 'Missing', 'meta': {}, 'seasons': [{'season_name': 'Temporada 1', 'episodes': [missing]}]}
        _, view, _ = self._build(anime)
        self.assertIsNone(view.content.controls[-1].controls[0].on_click)


class OrganizeTests(unittest.TestCase):
    class FakePage:
        def update(self): pass
        def run_thread(self, work): work()

    def _catalog(self, directory):
        store = LibraryStore(directory)
        action = store.upsert_anime('action', {'title': 'Action', 'genres': '["Ação", "Fantasia"]'})
        comedy = store.upsert_anime('comedy', {'title': 'Comedy', 'genres': '["Comédia", "Fantasia"]'})
        plain = store.upsert_anime('plain', {'title': 'Plain', 'genres': '[]'})
        paths = []
        for anime, name in ((action, 'action'), (comedy, 'comedy'), (plain, 'plain')):
            path = f'/library/{name}.mkv'
            store.upsert_episode(anime, path, f'{name} - 01.mkv', 1, 1)
            paths.append(path)
        return store, action, comedy, plain, paths

    def test_organize_summary_empty_and_uses_only_real_genres(self):
        self.assertEqual(LibraryService.organize_summary([]), {
            'genres': [],
            'states': [{'name': 'Todos', 'count': 0}, {'name': 'Favoritos', 'count': 0},
                       {'name': 'Em andamento', 'count': 0}, {'name': 'Concluídos', 'count': 0}],
        })
        with tempfile.TemporaryDirectory() as d:
            store, *_ = self._catalog(d)
            genres = LibraryService.organize_summary(store.catalog())['genres']
            self.assertEqual([(item['name'], item['count']) for item in genres],
                             [('Ação', 1), ('Comédia', 1), ('Fantasia', 2)])
            self.assertNotIn('Drama', [item['name'] for item in genres])

    def test_organize_filters_reuse_favorites_progress_and_missing_rules(self):
        with tempfile.TemporaryDirectory() as d:
            store, action, comedy, plain, paths = self._catalog(d)
            store.toggle_favorite(action)
            store.save_progress(paths[0], 20, 100)
            store.save_progress(paths[1], 95, 100)
            with store._conn() as con:
                con.execute('UPDATE episodes SET missing=1 WHERE path=?', (paths[2],))
            catalog = store.catalog()
            service = LibraryService(store)
            self.assertEqual({a['id'] for a in service.browse_catalog(catalog, genre='Fantasia')}, {action, comedy})
            self.assertEqual([a['id'] for a in service.browse_catalog(catalog, state='Favoritos', genre='Ação')], [action])
            self.assertEqual([a['id'] for a in service.browse_catalog(catalog, state='Em andamento', genre='Ação')], [action])
            self.assertEqual([a['id'] for a in service.browse_catalog(catalog, state='Concluídos', genre='Comédia')], [comedy])
            self.assertEqual(service.browse_catalog(catalog, genre='Drama'), [])
            self.assertEqual(service.continue_watching()[0]['anime_id'], action)

    def test_organize_summary_persists_and_matches_home_catalog_rules(self):
        with tempfile.TemporaryDirectory() as d:
            store, action, *_ = self._catalog(d)
            store.toggle_favorite(action)
            reopened = LibraryStore(d)
            catalog = reopened.catalog()
            summary = LibraryService.organize_summary(catalog)
            self.assertEqual(summary['states'][1]['count'], len(LibraryService.browse_catalog(catalog, state='Favoritos')))
            self.assertEqual(summary['states'][0]['count'], len(catalog))
            self.assertEqual([item['name'] for item in summary['genres']], ['Ação', 'Comédia', 'Fantasia'])

    def test_organize_view_builds_empty_catalog_and_navigates_selected_anime(self):
        with tempfile.TemporaryDirectory() as d:
            empty = OrganizeView.build(self.FakePage(), LibraryService(LibraryStore(d)), lambda _: None, lambda: None, lambda: None)
            self.assertEqual(empty.content.controls[0].__class__.__name__, 'Row')
        with tempfile.TemporaryDirectory() as d:
            store, action, *_ = self._catalog(d)
            selected = []
            view = OrganizeView.build(self.FakePage(), LibraryService(store), selected.append, lambda: None, lambda: None)

            def walk(control):
                yield control
                for child in getattr(control, 'controls', []) or []:
                    yield from walk(child)
                content = getattr(control, 'content', None)
                if content is not None:
                    yield from walk(content)

            genre = next(item for item in walk(view) if item.__class__.__name__ == 'Container' and
                         item.on_click and item.content.__class__.__name__ == 'Stack')
            genre.on_click(None)
            grid = next(item for item in walk(view) if item.__class__.__name__ == 'GridView')
            grid.controls[0].on_click(None)
            self.assertEqual(selected[0]['id'], action)


if __name__ == '__main__':
    unittest.main()
