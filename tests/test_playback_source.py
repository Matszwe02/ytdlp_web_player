import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from flask import Response


SOURCE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
if SOURCE_DIR not in sys.path:
    sys.path.insert(0, SOURCE_DIR)

import app as app_module


class PlaybackSourceTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config['TESTING'] = True
        self.client = app_module.app.test_client()

    def test_direct_uses_ready_local_video(self):
        with tempfile.NamedTemporaryFile(suffix='.mp4') as video_file:
            video_file.write(b'cached video')
            video_file.flush()
            with patch.object(app_module, 'get_ready_cached_video', return_value=video_file.name):
                response = self.client.head('/direct?url=https%3A%2F%2Fexample.com%2Fvideo&quality=720')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get('X-Playback-Source'), 'local')
            self.assertEqual(response.headers.get('Accept-Ranges'), 'bytes')
            response.close()

    def test_direct_stream_preference_never_checks_the_video_cache(self):
        with patch.object(app_module, 'get_ready_cached_video') as get_ready_cached_video:
            response = self.client.head(
                '/direct?url=https%3A%2F%2Fexample.com%2Fvideo&quality=720&playback=stream'
            )

        get_ready_cached_video.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('X-Playback-Source'), 'stream')

    def test_first_stream_request_proxies_a_new_url_descriptor(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.url') as descriptor:
            descriptor.write('https://cdn.example/video.mp4\n{\"User-Agent\": \"test\"}\nsession=value\n')
            descriptor.flush()
            downloader = MagicMock()
            downloader.run.return_value = descriptor.name

            with (
                patch.object(app_module, 'check_media', return_value=None),
                patch.object(app_module, 'MediaDownloader', return_value=downloader),
                patch.object(app_module, 'stream_media_file', return_value=Response('stream')) as stream_media_file,
            ):
                response = self.client.get(
                    '/direct?url=https%3A%2F%2Fexample.com%2Fvideo&quality=720&playback=stream'
                )

        stream_media_file.assert_called_once_with(
            'https://example.com/video',
            'https://cdn.example/video.mp4',
            '{"User-Agent": "test"}',
            'session=value',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('X-Playback-Source'), 'stream')

    def test_local_playback_supports_byte_ranges_for_seeking(self):
        with tempfile.NamedTemporaryFile(suffix='.mp4') as video_file:
            video_file.write(b'0123456789')
            video_file.flush()
            with patch.object(app_module, 'get_ready_cached_video', return_value=video_file.name):
                response = self.client.get(
                    '/direct?url=https%3A%2F%2Fexample.com%2Fvideo&quality=720&playback=local',
                    headers={'Range': 'bytes=2-5'},
                )

            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.data, b'2345')
            self.assertEqual(response.headers.get('Content-Range'), 'bytes 2-5/10')
            self.assertEqual(response.headers.get('X-Playback-Source'), 'local')
            response.close()


if __name__ == '__main__':
    unittest.main()
