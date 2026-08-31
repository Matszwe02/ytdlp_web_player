import os
import sys
import tempfile
import unittest
from unittest.mock import patch


SOURCE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
if SOURCE_DIR not in sys.path:
    sys.path.insert(0, SOURCE_DIR)

import addons
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
                patch.object(addons, 'get_data_dir', return_value=data_dir),
                patch.object(app_module, 'wait_for_video_cache', return_value=cached_video) as wait_for_video_cache,
                patch.object(app_module, 'get_meta', return_value={'title': 'Test Video'}),
                patch.object(app_module, 'MediaDownloader') as media_downloader,
            ):
                response = self.client.get(
                    '/download?url=https%3A%2F%2Fexample.com%2Fvideo&quality=720'
                )
                progress = addons.DownloadProgress.read(url, 'cache-720')
                response_data = response.get_data()
                content_disposition = response.headers.get('Content-Disposition')
                response.close()

        media_downloader.assert_not_called()
        wait_for_video_cache.assert_called_once_with(url, '720')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_data, b'ready cached video')
        self.assertIn('Test Video-720.mp4', content_disposition)
        self.assertEqual(progress['status'], 'ready')
        self.assertEqual(progress['percent'], 100)
        self.assertEqual(progress['downloaded_bytes'], len(b'ready cached video'))
        self.assertEqual(progress['total_bytes'], len(b'ready cached video'))

    def test_trim_waits_for_canonical_cache_before_deriving_download(self):
        url = 'https://example.com/video'
        with tempfile.NamedTemporaryFile(suffix='.mp4') as cached_video:
            with (
                patch.object(app_module, 'wait_for_video_cache', return_value=cached_video.name) as wait_for_video_cache,
                patch.object(app_module, 'get_meta', return_value={'title': 'Test Video'}),
                patch.object(app_module, 'host_file', return_value=app_module.Response('trimmed')) as host_file,
            ):
                response = self.client.get(
                    '/download?url=https%3A%2F%2Fexample.com%2Fvideo&quality=720&start=10&end=20'
                )

        wait_for_video_cache.assert_called_once_with(url, '720')
        host_file.assert_called_once()
        self.assertEqual(host_file.call_args.args[:2], (url, 'video-720_10.0-20.0'))
        self.assertEqual(response.data, b'trimmed')


if __name__ == '__main__':
    unittest.main()
