import re
import threading
import unittest
from pathlib import Path

from core.library_service import LibraryService

ROOT = Path(__file__).resolve().parents[1]
NATIVE_DIR = ROOT / 'android/app/src/main/kotlin/com/reiflix/reiflix_local'
BATCH_SIZE = 250

class ProbeStore:
    def __init__(self):
        self.run_id = 1
        self.progress = []
        self.account_data = {}
        self.scan = None
    def scan_by_id(self, scan_id):
        return self.scan
    def begin_scan(self, **kwargs):
        self.scan = {'id': self.run_id, 'scan_id': kwargs.get('scan_id'), 'status': 'running'}
        return self.run_id
    def latest_completed_native_generation(self, *args):
        return None
    def add_folder(self, *args, **kwargs):
        return None
    def account(self):
        return self.account_data
    def update_scan_progress(self, run_id, summary, **kwargs):
        self.progress.append(dict(summary))
        return True

class Prompt11BatchService(LibraryService):
    def __init__(self):
        self.store = ProbeStore()
        self._scan_lock = threading.Lock()
        self.artwork = None
    def _record_document(self, *, document, result, **kwargs):
        result.files += 1
        result.new += 1
        result.videos += 1
        return document['uri']

def documents(count, offset=0):
    for index in range(offset, offset + count):
        yield {'uri': f'content://prompt11/{index}', 'name': f'{index}.mp4'}

class TestPrompt11Scalability(unittest.TestCase):
    def run_load(self, total):
        service = Prompt11BatchService()
        peak_batch = 0
        processed = 0
        for start in range(0, total, BATCH_SIZE):
            batch = list(documents(min(BATCH_SIZE, total - start), start))
            peak_batch = max(peak_batch, len(batch))
            result = service.ingest_documents_batch(
                'broad-storage', batch, source_kind='broad_storage',
                scan_id='load-scan', scope_kind='volume', scope_ref='external_primary',
                scan_generation=1, generation_id='native:test:1',
                batch_id=f'batch-{start // BATCH_SIZE + 1}',
                batch_number=start // BATCH_SIZE + 1, batch_size=len(batch),
            )
            processed += int(result['processed'])
        self.assertEqual(processed, total)
        self.assertLessEqual(peak_batch, BATCH_SIZE)
        self.assertEqual(len(service.store.progress), (total + BATCH_SIZE - 1) // BATCH_SIZE)

    def test_10000_documents_incremental(self):
        self.run_load(10_000)

    def test_50000_documents_incremental(self):
        self.run_load(50_000)

    def test_100000_documents_incremental(self):
        self.run_load(100_000)

    def test_android_scanners_do_not_retain_global_document_arrays(self):
        broad = (NATIVE_DIR / 'BroadStorageScanner.kt').read_text(encoding='utf-8')
        saf = (NATIVE_DIR / 'SafScanner.kt').read_text(encoding='utf-8')
        media = (NATIVE_DIR / 'MediaStoreScanner.kt').read_text(encoding='utf-8')
        main = (NATIVE_DIR / 'MainActivity.kt').read_text(encoding='utf-8')
        for source in (broad, saf, media):
            self.assertIn('NativeBatch.Accumulator', source)
        self.assertNotIn('val docsByVolume =', broad)
        self.assertNotIn('val preparedDocuments =', broad)
        self.assertNotIn('val documents=JSONArray()', saf)
        self.assertNotIn('val documents=JSONArray()', media)
        self.assertIn('saf_scan_batch', main)
        self.assertIn('broad_storage_scan_batch', main)
        self.assertIn('mediastore_scan_batch', main)

    def test_batch_size_is_documented_and_bounded(self):
        native_batch = (NATIVE_DIR / 'NativeBatch.kt').read_text(encoding='utf-8')
        self.assertRegex(native_batch, r'DEFAULT_SIZE = 250')
        self.assertIn('value.coerceIn(MIN_SIZE, MAX_SIZE)', native_batch)

if __name__ == '__main__':
    unittest.main()
