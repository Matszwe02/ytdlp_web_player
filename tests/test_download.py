import os
import sys
import tempfile
import unittest
from unittest.mock import patch


SOURCE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
if SOURCE_DIR not in sys.path:
    sys.path.insert(0, SOURCE_DIR)

import app as app_module


class DownloadEndpointTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config['TESTING'] = True
        self.client = app_module.app.test_client()

    def test_current_quality_serves_ready_cache_without_reentering_downloader(self):
        url = 'https://example.com/video'
        with tempfile.TemporaryDirectory() as data_dir:
            cached_video = os.path.join(data_dir, 'video-720.mp4')
            with open(cached_video, 'wb') as video_file:
                video_file.write(b'ready cached video')

            with (
                patch.object(app_module, 'ensure_video_cache', return_value={'status': 'ready'}) as ensure_video_cache,
                patch.object(app_module, 'get_ready_cached_video', return_value=cached_video) as get_ready_cached_video,
                patch.object(app_module, 'get_meta', return_value={'title': 'Test Video'}),
                patch.object(app_module, 'MediaDownloader') as media_downloader,
            ):
                response = self.client.get(
                    '/download?url=https%3A%2F%2Fexample.com%2Fvideo&quality=720'
                )
                response_data = response.get_data()
                content_disposition = response.headers.get('Content-Disposition')
                response.close()

        media_downloader.assert_not_called()
        ensure_video_cache.assert_called_once_with(url, '720')
        get_ready_cached_video.assert_called_once_with(url, '720', validate=False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_data, b'ready cached video')
        self.assertIn('Test Video-720.mp4', content_disposition)

    def test_trim_waits_for_canonical_cache_before_deriving_download(self):
        url = 'https://example.com/video'
        with tempfile.NamedTemporaryFile(suffix='.mp4') as cached_video:
            with (
                patch.object(app_module, 'ensure_video_cache', return_value={'status': 'ready'}) as ensure_video_cache,
                patch.object(app_module, 'get_ready_cached_video', return_value=cached_video.name),
                patch.object(app_module, 'get_meta', return_value={'title': 'Test Video'}),
                patch.object(app_module, 'host_file', return_value=app_module.Response('trimmed')) as host_file,
            ):
                response = self.client.get(
                    '/download?url=https%3A%2F%2Fexample.com%2Fvideo&quality=720&start=10&end=20'
                )

        ensure_video_cache.assert_called_once_with(url, '720')
        host_file.assert_called_once()
        self.assertEqual(host_file.call_args.args[:2], (url, 'video-720_10.0-20.0'))
        self.assertEqual(response.data, b'trimmed')

    def test_audio_download_bypasses_video_cache(self):
        url = 'https://example.com/video'
        with (
            patch.object(app_module, 'ensure_video_cache') as ensure_video_cache,
            patch.object(app_module, 'get_meta', return_value={'title': 'Test Video'}),
            patch.object(app_module, 'host_file', return_value=app_module.Response('audio')) as host_file,
        ):
            response = self.client.get(
                '/download?url=https%3A%2F%2Fexample.com%2Fvideo&quality=audio'
            )

        ensure_video_cache.assert_not_called()
        host_file.assert_called_once_with(url, 'audio', download_name='Test Video')
        self.assertEqual(response.data, b'audio')

    def test_in_progress_cache_returns_immediately_without_a_file(self):
        state = {
            'status': 'downloading',
            'percent': 50,
            'downloaded_bytes': 50,
            'total_bytes': 100,
            'speed': 10,
        }
        with (
            patch.object(app_module, 'ensure_video_cache', return_value=state) as ensure_video_cache,
            patch.object(app_module, 'get_ready_cached_video') as get_ready_cached_video,
            patch.object(app_module, 'host_file') as host_file,
        ):
            response = self.client.get(
                '/download?url=https%3A%2F%2Fexample.com%2Fvideo&quality=720'
            )

        ensure_video_cache.assert_called_once_with('https://example.com/video', '720')
        get_ready_cached_video.assert_not_called()
        host_file.assert_not_called()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data, b'')
        self.assertEqual(response.headers.get('X-Cache-Status'), 'downloading')
        self.assertEqual(response.headers.get('Retry-After'), '1')
        self.assertEqual(response.headers.get('Cache-Control'), 'no-store')


if __name__ == '__main__':
    unittest.main()
