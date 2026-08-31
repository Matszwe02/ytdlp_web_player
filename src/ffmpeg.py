"""FFmpeg transcoding helpers."""

import os
import subprocess
import time
from functools import lru_cache
from hashlib import sha1


DEFAULT_VIDEO_ENCODER = 'libx264'
AUTO_VIDEO_ENCODER = 'auto'
SUPPORTED_VIDEO_ENCODERS = frozenset({AUTO_VIDEO_ENCODER, DEFAULT_VIDEO_ENCODER, 'h264_nvenc'})


@lru_cache(maxsize=None)
def nvenc_is_usable(ffmpeg_path: str) -> bool:
    """Check that NVENC can initialize, not only that FFmpeg was built with it."""
    command = [
        ffmpeg_path,
        '-hide_banner',
        '-loglevel', 'error',
        '-f', 'lavfi',
        '-i', 'color=size=256x256:rate=1',
        '-frames:v', '1',
        '-c:v', 'h264_nvenc',
        '-f', 'null',
        '-',
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


@lru_cache(maxsize=None)
def resolve_video_encoder(value: str | None, ffmpeg_path: str | None) -> str:
    """Select a usable H.264 encoder, falling back safely to libx264."""
    encoder = (value or AUTO_VIDEO_ENCODER).strip().lower()
    if encoder not in SUPPORTED_VIDEO_ENCODERS:
        print(
            f"Warning: unsupported FFMPEG_VIDEO_ENCODER={value!r}. "
            f"Supported values: {', '.join(sorted(SUPPORTED_VIDEO_ENCODERS))}. "
            f"Falling back to {DEFAULT_VIDEO_ENCODER}."
        )
        return DEFAULT_VIDEO_ENCODER

    if encoder == DEFAULT_VIDEO_ENCODER:
        return DEFAULT_VIDEO_ENCODER
    if not ffmpeg_path or not nvenc_is_usable(ffmpeg_path):
        print(f'Warning: NVENC is unavailable for FFMPEG_VIDEO_ENCODER={encoder!r}. Falling back to {DEFAULT_VIDEO_ENCODER}.')
        return DEFAULT_VIDEO_ENCODER
    return 'h264_nvenc'


def build_video_encoder_args(video_encoder: str, ffmpeg_path: str | None) -> list[str]:
    """Build output options for the configured H.264 video encoder."""
    encoder = resolve_video_encoder(video_encoder, ffmpeg_path)
    if encoder == DEFAULT_VIDEO_ENCODER:
        return ['-c:v', DEFAULT_VIDEO_ENCODER, '-crf', '22']
    return ['-c:v', 'h264_nvenc', '-preset', 'p5', '-rc', 'vbr', '-cq', '22', '-b:v', '0']


class FFMPEG:
    def __init__(self, url, ffmpeg_path=None, processes=None, proxy='', ffmpeg_command=None):
        """Provide ffmpeg_command to run synchronously. Check with ``success``."""
        self._p = None
        self.pid = None
        self.ffmpeg = ffmpeg_path
        self.processes = processes
        self.proxy = proxy
        self.ff_id = sha1(f'{time.time()}'.encode()).hexdigest()[:6]
        self.success = False
        self.stdout = ''
        self.start_time = time.time()
        self.url = url
        self.affected_files = []
        if ffmpeg_command and self.ffmpeg:
            self.run(ffmpeg_command)

    def kill(self):
        if self._p is None: return
        self.processes.rm(self.pid, kill=True)
        print(f'[FFMPEG {self.ff_id}] Killed')

    def run(self, ffmpeg_command):
        """Also runs synchronously, but can be placed in ``Thread``."""
        if not self.ffmpeg: return None
        ffmpeg_command = [self.ffmpeg] + ffmpeg_command
        ffmpeg_env = {f"{self.proxy.split('://')[0]}_proxy": self.proxy} if self.proxy else None
        print(f'[FFMPEG {self.ff_id}] Executing {ffmpeg_command}')
        self._p = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=ffmpeg_env)
        self.pid = self._p.pid
        self.processes.setitem(self.pid, [self.url, f'FFMPEG {self.ff_id}', time.time()])
        for line in self._p.stdout:
            line_out = line.decode().strip()
            print(f'[FFMPEG {self.ff_id}] {line_out}')
            self.stdout += line_out + '\n'
            if time.time() - self.start_time > 3600:
                self.kill()
                self.success = False
                raise TimeoutError()
        self._p.wait()
        self.processes.rm(self.pid)
        if self._p.returncode != 0:
            self.success = False
            for file in self.affected_files:
                if os.path.exists(file): os.remove(file)
            raise RuntimeError(f'FFMPEG exited unexpectedly with return code {self._p.returncode}')
        print(f'[FFMPEG {self.ff_id}] Finished')
        self.success = True
