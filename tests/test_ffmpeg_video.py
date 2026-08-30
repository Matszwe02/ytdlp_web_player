import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from ffmpeg_video import (
    DEFAULT_VIDEO_ENCODER,
    build_video_encoder_args,
    resolve_video_encoder,
)


class FFMpegVideoConfigTests(unittest.TestCase):
    def test_default_encoder_is_libx264(self):
        self.assertEqual(resolve_video_encoder(None), 'libx264')
        self.assertEqual(
            build_video_encoder_args(DEFAULT_VIDEO_ENCODER),
            ['-c:v', 'libx264', '-crf', '22'],
        )

    def test_nvenc_encoder_arguments(self):
        self.assertEqual(resolve_video_encoder('h264_nvenc'), 'h264_nvenc')
        self.assertEqual(
            build_video_encoder_args('h264_nvenc'),
            ['-c:v', 'h264_nvenc', '-preset', 'p5', '-rc', 'vbr', '-cq', '22', '-b:v', '0'],
        )

    def test_invalid_encoder_logs_and_falls_back_to_libx264(self):
        messages = []

        self.assertEqual(resolve_video_encoder('vaapi', messages.append), 'libx264')
        self.assertIn('Unsupported FFMPEG_VIDEO_ENCODER', messages[0])
        self.assertIn('Falling back to libx264', messages[0])


if __name__ == '__main__':
    unittest.main()
