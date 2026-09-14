"""FFmpeg transcoding helpers."""

import os
import subprocess
import time
from functools import lru_cache
from hashlib import sha1


DEFAULT_VIDEO_ENCODER = 'libx264'
NVENC_VIDEO_ENCODER = 'h264_nvenc'


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
        '-c:v', NVENC_VIDEO_ENCODER,
        '-f', 'null',
        '-',
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


@lru_cache(maxsize=None)
def resolve_hardware_encoder(ffmpeg_path: str | None) -> str | None:
    """Return the best available hardware H.264 encoder, if any."""
    if ffmpeg_path and nvenc_is_usable(ffmpeg_path):
        return NVENC_VIDEO_ENCODER
    return None


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
        if self.processes:
            self.processes.rm(self.pid, kill=True)
        else:
            self._p.kill()
        print(f'[FFMPEG {self.ff_id}] Killed')

    def _cleanup_affected_files(self):
        for file in self.affected_files:
            if os.path.exists(file):
                os.remove(file)

    def _hardware_command(self, ffmpeg_command):
        """Replace libx264 output options with the best available hardware encoder."""
        command = list(ffmpeg_command)
        try:
            encoder_index = command.index('-c:v')
        except ValueError:
            return None

        if encoder_index + 1 >= len(command) or command[encoder_index + 1] != DEFAULT_VIDEO_ENCODER:
            return None

        hardware_encoder = resolve_hardware_encoder(self.ffmpeg)
        if hardware_encoder != NVENC_VIDEO_ENCODER:
            return None

        quality = '22'
        if '-crf' in command:
            crf_index = command.index('-crf')
            if crf_index + 1 < len(command):
                quality = command[crf_index + 1]
                del command[crf_index:crf_index + 2]

        if '-preset' in command:
            preset_index = command.index('-preset')
            if preset_index + 1 < len(command):
                del command[preset_index:preset_index + 2]

        encoder_index = command.index('-c:v')
        command[encoder_index + 1] = NVENC_VIDEO_ENCODER
        command[encoder_index + 2:encoder_index + 2] = [
            '-preset', 'p5',
            '-rc', 'vbr',
            '-cq', quality,
            '-b:v', '0',
        ]
        return command

    def _run_once(self, ffmpeg_command):
        command = [self.ffmpeg] + list(ffmpeg_command)
        ffmpeg_env = os.environ.copy()
        if self.proxy:
            ffmpeg_env[f"{self.proxy.split('://')[0]}_proxy"] = self.proxy

        print(f'[FFMPEG {self.ff_id}] Executing {command}')
        self._p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=ffmpeg_env)
        self.pid = self._p.pid
        if self.processes:
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
        if self.processes:
            self.processes.rm(self.pid)

        if self._p.returncode != 0:
            self.success = False
            self._cleanup_affected_files()
            raise RuntimeError(f'FFMPEG exited unexpectedly with return code {self._p.returncode}')

        print(f'[FFMPEG {self.ff_id}] Finished')
        self.success = True

    def run(self, ffmpeg_command):
        """Run synchronously, preferring hardware encoding with an automatic CPU fallback."""
        if not self.ffmpeg: return None

        software_command = list(ffmpeg_command)
        hardware_command = self._hardware_command(software_command)

        if hardware_command:
            print(f'[FFMPEG {self.ff_id}] Using hardware encoder {NVENC_VIDEO_ENCODER}')
            try:
                self._run_once(hardware_command)
                return None
            except RuntimeError:
                if self._p and self._p.returncode is not None and self._p.returncode < 0:
                    raise
                print(f'[FFMPEG {self.ff_id}] Hardware encoding failed, retrying with {DEFAULT_VIDEO_ENCODER}')
                self.success = False
                self.start_time = time.time()

        self._run_once(software_command)
        return None
