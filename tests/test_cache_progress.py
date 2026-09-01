import os
import json
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


SOURCE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
if SOURCE_DIR not in sys.path:
    sys.path.insert(0, SOURCE_DIR)

import addons
import app as app_module


class DeferredThread:
    instances = []

    def __init__(self, target, args=(), daemon=None):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.started = False
        self.instances.append(self)

    def start(self):
        self.started = True


class CacheProgressStoreTests(unittest.TestCase):
    def test_progress_state_is_written_with_atomic_replace(self):
        state = {
            'status': 'downloading',
            'percent': 25,
            'downloaded_bytes': 25,
            'total_bytes': 100,
            'speed': 5,
        }

        with tempfile.TemporaryDirectory() as data_dir:
            with (
                patch.object(addons, 'get_data_dir', return_value=data_dir),
                patch.object(addons.os, 'replace', wraps=os.replace) as replace,
            ):
                store = addons.CacheProgressStore('https://example.com/video', 'cache-720')
                store.write(state)

                self.assertEqual(store.read(), state)
                replace.assert_called_once()
                temp_path, destination = replace.call_args.args
                self.assertEqual(destination, store.path)
                self.assertFalse(os.path.exists(temp_path))

    def test_invalid_progress_id_is_not_read_or_written(self):
        with tempfile.TemporaryDirectory() as data_dir:
            with patch.object(addons, 'get_data_dir', return_value=data_dir):
                store = addons.CacheProgressStore(
                    'https://example.com/video', '../../unsafe'
                )
                store.write({'status': 'ready'})

                self.assertIsNone(store.read())
                self.assertEqual(os.listdir(data_dir), [])


class CacheProgressTests(unittest.TestCase):
    def setUp(self):
        DeferredThread.instances = []

    def test_cache_quality_is_restricted_to_numeric_or_best(self):
        self.assertEqual(addons.normalize_cache_quality('720'), '720')
        self.assertEqual(addons.normalize_cache_quality('best'), 'best')
        self.assertIsNone(addons.normalize_cache_quality('audio'))
        self.assertIsNone(addons.normalize_cache_quality('../../video'))

    def test_cache_progress_survives_a_new_reader(self):
        with tempfile.TemporaryDirectory() as data_dir:
            with (
                patch.object(addons, 'get_data_dir', return_value=data_dir),
                patch.object(addons, 'get_ready_cached_video', return_value=None),
            ):
                progress = addons.DownloadProgress('https://example.com/video', 'cache-720')
                progress.download({
                    'status': 'downloading',
                    'downloaded_bytes': 25_000_000,
                    'total_bytes': 100_000_000,
                    'speed': 5_000_000,
                })

                state = addons.read_video_cache_progress('https://example.com/video', '720')

        self.assertEqual(state['status'], 'downloading')
        self.assertEqual(state['percent'], 25)
        self.assertEqual(state['downloaded_bytes'], 25_000_000)
        self.assertEqual(state['total_bytes'], 100_000_000)
        self.assertEqual(state['speed'], 5_000_000)

    def test_cache_progress_aggregates_concurrent_video_and_audio_downloads(self):
        with tempfile.TemporaryDirectory() as data_dir:
            with (
                patch.object(addons, 'get_data_dir', return_value=data_dir),
                patch.object(addons, 'get_ready_cached_video', return_value=None),
            ):
                video = addons.DownloadProgress('https://example.com/video', 'cache-720')
                video.download({
                    'status': 'downloading',
                    'downloaded_bytes': 80_000_000,
                    'total_bytes': 100_000_000,
                    'speed': 5_000_000,
                })
                audio = addons.DownloadProgress(
                    'https://example.com/video', addons.CACHE_AUDIO_PROGRESS_ID
                )
                audio.download({
                    'status': 'downloading',
                    'downloaded_bytes': 10_000_000,
                    'total_bytes': 20_000_000,
                    'speed': 2_000_000,
                })

                state = addons.read_video_cache_progress('https://example.com/video', '720')

        self.assertEqual(state['status'], 'downloading')
        self.assertEqual(state['percent'], 75)
        self.assertEqual(state['downloaded_bytes'], 90_000_000)
        self.assertEqual(state['total_bytes'], 120_000_000)
        self.assertEqual(state['speed'], 7_000_000)

    def test_hls_fixup_does_not_mark_cache_as_encoding(self):
        with tempfile.TemporaryDirectory() as data_dir:
            with patch.object(addons, 'get_data_dir', return_value=data_dir):
                progress = addons.DownloadProgress('https://example.com/video', 'cache-720')
                progress.download({
                    'status': 'finished',
                    'downloaded_bytes': 100_000_000,
                    'total_bytes': 100_000_000,
                })
                progress.handle_ytdlp_event({
                    'type': 'postprocessor',
                    'status': 'started',
                    'postprocessor': 'FixupM3u8',
                })
                state = addons.CacheProgressStore(
                    'https://example.com/video', 'cache-720'
                ).read()

        self.assertEqual(state['status'], 'downloading')
        self.assertEqual(state['percent'], 100)

    def test_audio_download_publishes_shared_cache_progress_until_ready(self):
        with tempfile.TemporaryDirectory() as data_dir:
            downloader = addons.MediaDownloader.__new__(addons.MediaDownloader)
            downloader.url = 'https://example.com/video'
            downloader.data_dir = data_dir
            downloader.media_type = 'audio'
            downloader.progress = None
            downloader.meta = {}
            downloader.ydl_opts = {}
            observed_states = []

            def download_audio(_url, _opts, callback):
                callback({
                    'type': 'download',
                    'status': 'downloading',
                    'downloaded_bytes': 5_000_000,
                    'total_bytes': 20_000_000,
                    'speed': 2_000_000,
                })
                observed_states.append(addons.CacheProgressStore(
                    downloader.url, addons.CACHE_AUDIO_PROGRESS_ID
                ).read())
                with open(os.path.join(data_dir, 'audio.mp3'), 'wb') as audio_file:
                    audio_file.write(b'complete audio')

            with (
                patch.object(addons, 'get_data_dir', return_value=data_dir),
                patch.object(addons.YTDLP, 'download', side_effect=download_audio),
            ):
                downloader.audio()
                final_state = addons.CacheProgressStore(
                    downloader.url, addons.CACHE_AUDIO_PROGRESS_ID
                ).read()

        self.assertEqual(observed_states[0]['status'], 'downloading')
        self.assertEqual(observed_states[0]['percent'], 25)
        self.assertEqual(final_state['status'], 'ready')
        self.assertEqual(final_state['downloaded_bytes'], len(b'complete audio'))

    def test_cache_progress_persists_ffmpeg_encoding_state(self):
        with tempfile.TemporaryDirectory() as data_dir:
            with (
                patch.object(addons, 'get_data_dir', return_value=data_dir),
                patch.object(addons, 'get_ready_cached_video', return_value=None),
            ):
                progress = addons.DownloadProgress('https://example.com/video', 'cache-720')
                progress.encoding()
                state = addons.read_video_cache_progress('https://example.com/video', '720')

        self.assertEqual(state['status'], 'encoding')
        self.assertEqual(state['percent'], 100)

    def test_repeated_cache_start_requests_launch_one_worker(self):
        with tempfile.TemporaryDirectory() as data_dir:
            with (
                patch.object(addons, 'get_data_dir', return_value=data_dir),
                patch.object(addons, 'get_ready_cached_video', return_value=None),
                patch.object(addons, 'Thread', DeferredThread),
            ):
                first = addons.ensure_video_cache('https://example.com/video', '720')
                second = addons.ensure_video_cache('https://example.com/video', '720')

        self.assertEqual(first['status'], 'preparing')
        self.assertEqual(second['status'], 'preparing')
        self.assertEqual(len(DeferredThread.instances), 1)
        self.assertTrue(DeferredThread.instances[0].started)
        self.assertTrue(DeferredThread.instances[0].daemon)

    def test_existing_progress_is_queried_without_resuming_cache_job(self):
        with tempfile.TemporaryDirectory() as data_dir:
            with (
                patch.object(addons, 'get_data_dir', return_value=data_dir),
                patch.object(addons, 'get_ready_cached_video', return_value=None),
            ):
                progress = addons.DownloadProgress('https://example.com/video', 'cache-720')
                progress.error('previous job failed')

                with patch.object(addons, 'ensure_video_cache') as ensure_video_cache:
                    state = addons.start_video_cache_if_new('https://example.com/video', '720')

        ensure_video_cache.assert_not_called()
        self.assertEqual(state['status'], 'error')

    def test_brand_new_cache_state_starts_background_job(self):
        with tempfile.TemporaryDirectory() as data_dir:
            expected = addons.DownloadProgress.initial_state()
            with (
                patch.object(addons, 'get_data_dir', return_value=data_dir),
                patch.object(addons, 'get_ready_cached_video', return_value=None),
                patch.object(addons, 'ensure_video_cache', return_value=expected) as ensure_video_cache,
            ):
                state = addons.start_video_cache_if_new('https://example.com/video', '720')

        ensure_video_cache.assert_called_once_with('https://example.com/video', '720')
        self.assertEqual(state, expected)

    def test_ready_state_is_derived_from_validated_cached_video(self):
        with tempfile.TemporaryDirectory() as data_dir:
            video_path = os.path.join(data_dir, 'video-720.mp4')
            with open(video_path, 'wb') as video_file:
                video_file.write(b'ready video')

            with (
                patch.object(addons, 'get_data_dir', return_value=data_dir),
                patch.object(addons, 'get_ready_cached_video', return_value=video_path),
            ):
                state = addons.read_video_cache_progress('https://example.com/video', '720')

        self.assertEqual(state['status'], 'ready')
        self.assertEqual(state['downloaded_bytes'], len(b'ready video'))
        self.assertEqual(state['total_bytes'], len(b'ready video'))

    def test_simultaneous_cache_requests_start_one_canonical_job(self):
        with tempfile.TemporaryDirectory() as data_dir:
            barrier = threading.Barrier(2)
            results = []
            errors = []

            def request_cache():
                try:
                    barrier.wait()
                    results.append(addons.ensure_video_cache('https://example.com/video', '720'))
                except Exception as error:
                    errors.append(error)

            with (
                patch.object(addons, 'get_data_dir', return_value=data_dir),
                patch.object(addons, 'get_ready_cached_video', return_value=None),
                patch.object(addons, 'Thread', DeferredThread),
            ):
                requests = [threading.Thread(target=request_cache) for _ in range(2)]
                for request in requests:
                    request.start()
                for request in requests:
                    request.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertTrue(all(state['status'] == 'preparing' for state in results))
        self.assertEqual(len(DeferredThread.instances), 1)


class CacheProgressEndpointTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config['TESTING'] = True
        self.client = app_module.app.test_client()

    def test_removed_legacy_cache_endpoints_return_not_found(self):
        requests = (
            ('GET', '/download-progress'),
            ('POST', '/cache'),
            ('GET', '/cache-progress'),
        )
        for method, path in requests:
            with self.subTest(path=path):
                response = self.client.open(path, method=method)
                self.assertEqual(response.status_code, 404)

    def test_sse_starts_cache_once_and_streams_changed_states_until_ready(self):
        downloading = {
            'status': 'downloading',
            'percent': 25,
            'downloaded_bytes': 25,
            'total_bytes': 100,
            'speed': 5,
        }
        ready = {
            'status': 'ready',
            'percent': 100,
            'downloaded_bytes': 100,
            'total_bytes': 100,
            'speed': 0,
        }

        with (
            patch.object(app_module, 'start_video_cache_if_new') as start_video_cache_if_new,
            patch.object(
                app_module,
                'read_video_cache_progress',
                side_effect=[downloading, downloading, ready],
            ),
            patch.object(app_module.time, 'sleep'),
        ):
            response = self.client.get(
                '/cache-progress-stream?url=https%3A%2F%2Fexample.com%2Fvideo&quality=720'
            )
            body = response.get_data(as_text=True)

        start_video_cache_if_new.assert_called_once_with('https://example.com/video', '720')
        events = [
            json.loads(line.removeprefix('data: '))
            for line in body.splitlines()
            if line.startswith('data: ')
        ]
        self.assertEqual(events, [downloading, ready])
        self.assertEqual(response.mimetype, 'text/event-stream')
        self.assertEqual(response.headers.get('Cache-Control'), 'no-cache, no-transform')
        self.assertEqual(response.headers.get('X-Accel-Buffering'), 'no')

    def test_sse_rejects_unsafe_quality_before_opening_stream(self):
        response = self.client.get(
            '/cache-progress-stream?url=https%3A%2F%2Fexample.com%2Fvideo&quality=invalid'
        )
        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
