import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SOURCE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
if SOURCE_DIR not in sys.path:
    sys.path.insert(0, SOURCE_DIR)

import addons


class CachedMediaCompatibilityTests(unittest.TestCase):
    @staticmethod
    def probe_result(*streams):
        return subprocess.CompletedProcess(
            args=['ffprobe'],
            returncode=0,
            stdout=json.dumps({'streams': list(streams)}),
            stderr='',
        )

    def test_mp3_audio_in_mp4_is_rejected(self):
        result = self.probe_result(
            {'codec_type': 'video', 'codec_name': 'h264'},
            {'codec_type': 'audio', 'codec_name': 'mp3'},
        )
        with (
            patch.object(addons.shutil, 'which', return_value='/usr/bin/ffprobe'),
            patch.object(addons.subprocess, 'run', return_value=result),
        ):
            self.assertFalse(addons.is_compatible_cached_media('/cache/video-720.mp4', 'video-720'))

    def test_aac_audio_in_mp4_is_accepted(self):
        result = self.probe_result(
            {'codec_type': 'video', 'codec_name': 'h264'},
            {'codec_type': 'audio', 'codec_name': 'aac'},
        )
        with (
            patch.object(addons.shutil, 'which', return_value='/usr/bin/ffprobe'),
            patch.object(addons.subprocess, 'run', return_value=result),
        ):
            self.assertTrue(addons.is_compatible_cached_media('/cache/video-720.mp4', 'video-720'))

    def test_video_only_mp4_is_rejected(self):
        result = self.probe_result({'codec_type': 'video', 'codec_name': 'h264'})
        with (
            patch.object(addons.shutil, 'which', return_value='/usr/bin/ffprobe'),
            patch.object(addons.subprocess, 'run', return_value=result),
        ):
            self.assertFalse(addons.is_compatible_cached_media('/cache/video-720.mp4', 'video-720'))

    def test_non_video_cache_does_not_invoke_ffprobe(self):
        with patch.object(addons.subprocess, 'run') as run:
            self.assertTrue(addons.is_compatible_cached_media('/cache/audio.mp3', 'audio'))
        run.assert_not_called()

    def test_ready_cached_video_requires_video_and_audio(self):
        with tempfile.TemporaryDirectory() as data_dir:
            video_path = os.path.join(data_dir, 'video-720.mp4')
            with open(video_path, 'wb') as video_file:
                video_file.write(b'media')

            streams = [
                {'codec_type': 'video', 'codec_name': 'h264'},
                {'codec_type': 'audio', 'codec_name': 'aac'},
            ]
            with (
                patch.object(addons, 'get_data_dir', return_value=data_dir),
                patch.object(addons, 'check_media', return_value=video_path),
                patch.object(addons, 'probe_media_streams', return_value=streams),
            ):
                self.assertEqual(
                    addons.get_ready_cached_video('https://example.com/video', '720'),
                    video_path,
                )

            with (
                patch.object(addons, 'get_data_dir', return_value=data_dir),
                patch.object(addons, 'check_media', return_value=video_path),
                patch.object(addons, 'probe_media_streams', return_value=streams[:1]),
            ):
                self.assertIsNone(addons.get_ready_cached_video('https://example.com/video', '720'))

    def test_active_cache_job_is_never_used_for_playback(self):
        with tempfile.TemporaryDirectory() as data_dir:
            with (
                patch.object(addons, 'get_data_dir', return_value=data_dir),
                patch.object(addons, 'check_media') as check_media,
            ):
                lock_store = addons.CacheLockStore('https://example.com/video', 'video-720')
                self.assertTrue(lock_store.try_acquire_media_lock())
                try:
                    self.assertIsNone(addons.get_ready_cached_video('https://example.com/video', '720'))
                finally:
                    lock_store.release_media_lock()
            check_media.assert_not_called()


if __name__ == '__main__':
    unittest.main()
