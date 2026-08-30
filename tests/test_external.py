import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from external import External


class ExternalFFmpegTests(unittest.TestCase):
    def test_ffmpeg_video_module_is_not_treated_as_bundled_executable(self):
        with tempfile.TemporaryDirectory() as app_dir:
            Path(app_dir, 'ffmpeg_video.py').touch()
            fallback_path = Path(app_dir, 'pyffmpeg-bin')
            pyffmpeg = types.SimpleNamespace(
                FFmpeg=lambda: types.SimpleNamespace(get_ffmpeg_bin=lambda: str(fallback_path))
            )

            with (
                patch('external.shutil.which', return_value=None),
                patch('external.os.path.dirname', return_value=app_dir),
                patch.dict(sys.modules, {'pyffmpeg': pyffmpeg}),
            ):
                self.assertEqual(External.download_ffmpeg(), str(fallback_path.resolve()))

    def test_path_ffmpeg_has_priority_over_bundled_binary(self):
        with tempfile.TemporaryDirectory() as app_dir:
            bundled = Path(app_dir, 'ffmpeg')
            bundled.touch()
            bundled.chmod(0o755)
            path_ffmpeg = Path(app_dir, 'from-path', 'ffmpeg')

            with (
                patch('external.shutil.which', return_value=str(path_ffmpeg)),
                patch('external.os.path.dirname', return_value=app_dir),
            ):
                self.assertEqual(External.download_ffmpeg(), str(path_ffmpeg.resolve()))


if __name__ == '__main__':
    unittest.main()
