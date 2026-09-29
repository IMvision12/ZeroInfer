"""Cache maintenance uses temporary folders; never touches installed models."""
import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.events import HUB
from services import store_service as store
from engine import Engine
import embedding_backend

# The stdio runner installs its transport on import. Restore the test process's
# streams and event sink immediately; main() and hardware polling are not run.
saved_stdout, saved_sink = sys.stdout, HUB._sink
try:
    runner = importlib.import_module('runner')
finally:
    sys.stdout = saved_stdout
    HUB.set_sink(saved_sink)


class CacheTests(unittest.TestCase):
    def test_removal_refuses_busy_engine_and_downloads(self):
        for lock in (runner._INFERENCE_LOCK, runner.ENGINE.cache_lock):
            lock.acquire()
            try:
                with self.assertRaises(RuntimeError):
                    with runner._cache_maintenance():
                        self.fail('Maintenance must not start')
            finally:
                lock.release()
        with runner._cache_maintenance():
            self.assertTrue(runner._INFERENCE_LOCK.locked())
        self.assertFalse(runner._INFERENCE_LOCK.locked())

    def test_partial_removal_preserves_failed_library_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'cache'
            (root / 'models--test--blocked').mkdir(parents=True)
            with patch.dict(os.environ, {'ZEROINFER_DATA_DIR': str(Path(directory) / 'data')}):
                store.mark_installed('test/blocked', {'task': 'text-generation'})
                store.mark_installed('test/removed', {'task': 'text-generation'})
                with patch.object(runner.hf, '_cache_roots', return_value=[root]), \
                     patch.object(runner.shutil, 'rmtree', side_effect=PermissionError('File is in use')):
                    result = runner._clear_hf_cache_files()
                self.assertFalse(result['ok'])
                self.assertIn('File is in use', result['error'])
                self.assertEqual(list(store.list_installed()), ['test/blocked'])

    def test_api_embeddings_are_listed_and_unloaded(self):
        with patch.dict(embedding_backend._CACHE, {'test/embed': object()}, clear=True):
            engine = Engine()
            self.assertIn('test/embed', engine.loaded_model_ids())
            with patch('engine._empty_torch_cache'):
                engine.unload('test/embed')
            self.assertEqual(engine.loaded_model_ids(), [])
