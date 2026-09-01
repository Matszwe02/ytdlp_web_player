import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse


SOURCE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
if SOURCE_DIR not in sys.path:
    sys.path.insert(0, SOURCE_DIR)

import addons
from app import app


class StreamProxyTests(unittest.TestCase):
    def test_relative_hls_segments_resolve_against_final_playlist_url(self):
        upstream = MagicMock()
        upstream.status_code = 200
        upstream.headers = {'Content-Type': 'application/vnd.apple.mpegurl'}
        upstream.content = b'#EXTM3U\n#EXTINF:5.0,\nsegments/part-001.ts\n'
        upstream.url = 'https://cdn.example/media/master/playlist.m3u8?token=abc'
        upstream.raise_for_status.return_value = None

        with (
            app.test_request_context('/external'),
            patch.object(addons.requests, 'get', return_value=upstream),
        ):
            response = addons.stream_media_file(
                'https://video.example/watch/123',
                'https://redirect.example/playlist.m3u8',
                '{"User-Agent": "test"}',
                'session=value',
            )

        segment_line = response.get_data(as_text=True).splitlines()[-1]
        query = parse_qs(urlparse(segment_line).query)
        self.assertEqual(
            query['src'][0],
            'https://cdn.example/media/master/segments/part-001.ts',
        )

    def test_relative_hls_tag_uris_use_the_same_playlist_base(self):
        upstream = MagicMock()
        upstream.status_code = 200
        upstream.headers = {'Content-Type': 'application/x-mpegURL'}
        upstream.content = b'#EXTM3U\n#EXT-X-MAP:URI="init/video.mp4"\nsegment.ts\n'
        upstream.url = 'https://cdn.example/path/playlist.m3u8'
        upstream.raise_for_status.return_value = None

        with (
            app.test_request_context('/external'),
            patch.object(addons.requests, 'get', return_value=upstream),
        ):
            response = addons.stream_media_file(
                'https://video.example/watch/123',
                'https://cdn.example/path/playlist.m3u8',
            )

        playlist = response.get_data(as_text=True)
        self.assertIn(
            'src=https%3A%2F%2Fcdn.example%2Fpath%2Finit%2Fvideo.mp4',
            playlist,
        )

    def test_mislabeled_m3u8_playlist_is_still_rewritten(self):
        upstream = MagicMock()
        upstream.status_code = 200
        upstream.headers = {'Content-Type': 'application/octet-stream'}
        upstream.content = b'#EXTM3U\nsegment.ts\n'
        upstream.url = 'https://cdn.example/path/playlist.m3u8?token=abc'
        upstream.raise_for_status.return_value = None

        with (
            app.test_request_context('/external'),
            patch.object(addons.requests, 'get', return_value=upstream),
        ):
            response = addons.stream_media_file(
                'https://video.example/watch/123',
                upstream.url,
            )

        self.assertIn(
            'src=https%3A%2F%2Fcdn.example%2Fpath%2Fsegment.ts',
            response.get_data(as_text=True),
        )


if __name__ == '__main__':
    unittest.main()
