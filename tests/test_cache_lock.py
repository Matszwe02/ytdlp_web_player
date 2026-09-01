import os
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


SOURCE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
if SOURCE_DIR not in sys.path:
    sys.path.insert(0, SOURCE_DIR)

import addons


class CacheLockStoreTests(unittest.TestCase):
    def test_job_lock_check_and_acquisition_is_atomic(self):
        with tempfile.TemporaryDirectory() as data_dir:
            barrier = threading.Barrier(2)
            acquisitions = []

            def acquire():
                store = addons.CacheLockStore('https://example.com/video', 'video-720')
                barrier.wait()
                acquisitions.append(store.try_acquire_job_lock())

            with patch.object(addons, 'get_data_dir', return_value=data_dir):
                threads = [threading.Thread(target=acquire) for _ in range(2)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

                store = addons.CacheLockStore('https://example.com/video', 'video-720')
                self.assertEqual(sorted(acquisitions), [False, True])
                self.assertTrue(store.job_lock_exists())
                self.assertTrue(store.release_job_lock())
                self.assertFalse(store.job_lock_exists())

    def test_active_media_lock_prevents_stale_job_lock_removal(self):
        with tempfile.TemporaryDirectory() as data_dir:
            with patch.object(addons, 'get_data_dir', return_value=data_dir):
                store = addons.CacheLockStore('https://example.com/video', 'video-720')
                self.assertTrue(store.try_acquire_job_lock())
                os.utime(store.job_lock_path, (0, 0))
                self.assertTrue(store.try_acquire_media_lock())

                self.assertFalse(store.remove_stale_job_lock(max_age=0))
                self.assertTrue(store.job_lock_exists())

                store.release_media_lock()
                self.assertTrue(store.remove_stale_job_lock(max_age=0))
                self.assertFalse(store.job_lock_exists())


class FileCachingLockTests(unittest.TestCase):
    def test_concurrent_requests_only_generate_media_once(self):
        with tempfile.TemporaryDirectory() as data_dir:
            media_path = os.path.join(data_dir, 'video-720.mp4')
            barrier = threading.Barrier(2)
            work_count = 0
            results = []
            errors = []
            state_lock = threading.Lock()

            def check_cached_media(**_kwargs):
                return media_path if os.path.exists(media_path) else None

            def worker():
                nonlocal work_count
                try:
                    lock = addons.FileCachingLock('https://example.com/video', 'video-720')
                    lock.max_wait_attempts = 100
                    lock.retry_interval_seconds = 0.005
                    barrier.wait()
                    with lock as cached_media:
                        if cached_media:
                            results.append(cached_media)
                            return
                        with state_lock:
                            work_count += 1
                        time.sleep(0.05)
                        with open(media_path, 'wb') as media_file:
                            media_file.write(b'complete video')
                        results.append(media_path)
                except Exception as error:
                    errors.append(error)

            with (
                patch.object(addons, 'get_data_dir', return_value=data_dir),
                patch.object(addons, 'check_media', side_effect=check_cached_media),
                patch.object(addons, 'keepalive'),
            ):
                threads = [threading.Thread(target=worker) for _ in range(2)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

            self.assertEqual(errors, [])
            self.assertEqual(work_count, 1)
            self.assertEqual(results, [media_path, media_path])
            self.assertFalse(os.path.exists(os.path.join(data_dir, 'video-720.temp')))

    def test_lock_is_released_when_cache_check_fails(self):
        with tempfile.TemporaryDirectory() as data_dir:
            with (
                patch.object(addons, 'get_data_dir', return_value=data_dir),
                patch.object(addons, 'check_media', side_effect=RuntimeError('cache failure')),
                patch.object(addons, 'keepalive'),
            ):
                lock = addons.FileCachingLock('https://example.com/video', 'video-720')
                with self.assertRaisesRegex(RuntimeError, 'cache failure'):
                    lock.__enter__()

            self.assertFalse(os.path.exists(lock.lock_path))


if __name__ == '__main__':
    unittest.main()
