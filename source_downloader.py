import pip
import shlex
import importlib
import os
import platform
import requests
import zipfile, tarfile
import shutil
import io
import subprocess
import re
import random
import time
import yt_dlp
import yt_dlp.version


FFMPEG = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"
FFMPEG_ARM64 = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linuxarm64-gpl.tar.xz"
FFMPEG_WIN = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"


os.environ['PATH'] = os.pathsep.join([os.getcwd(), os.environ['PATH']])
ffmpeg_version = '-'

class Downloader:

    def download_ytdlp():
        global yt_dlp
        pip.main(shlex.split('install --upgrade yt-dlp'))
        try:
            importlib.reload(yt_dlp)
            importlib.reload(yt_dlp.version)
        except:
            import yt_dlp
            import yt_dlp.version



    def download_ffmpeg():
        if os.path.exists('ffmpeg'): os.remove('ffmpeg')
        if os.path.exists('ffprobe'): os.remove('ffprobe')
        if os.path.exists('ffmpeg.exe'): os.remove('ffmpeg.exe')
        if os.path.exists('ffprobe.exe'): os.remove('ffprobe.exe')
        
        print('Downloading FFmpeg...')
        if platform.system() == 'Windows':
            url = FFMPEG_WIN
        else:
            if platform.machine() == 'aarch64' or platform.machine() == 'arm64':
                url = FFMPEG_ARM64
            else:
                url = FFMPEG
        
        response = requests.get(url)
        
        if platform.system() == 'Windows':
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                z.extractall('temp')
        else:
            with tarfile.open(fileobj=io.BytesIO(response.content), mode='r|*') as tar:
                tar.extractall('temp')
        
        
        # Search for ffmpeg and ffprobe executables
        for root, dirs, files in os.walk('temp'):
            for file in files:
                if file.lower() in ['ffprobe', 'ffmpeg', 'ffprobe.exe', 'ffmpeg.exe'] and os.path.split(root)[-1] == 'bin':
                    src = os.path.join(root, file)
                    dst = os.path.join(os.getcwd(), file).split('.')[0]
                    if src != dst:
                        shutil.copy(src, dst)
                        
                        if platform.system() == 'Windows':
                            shutil.copy(src, dst + '.exe')
                        else:
                            if not os.access(dst, os.X_OK):
                                print(f'Making {dst} executable...')
                                os.chmod(dst, 0o755)
                                print(f'{dst} is now executable')
                            else:
                                print(f'{dst} is already executable')

        shutil.rmtree('temp')
        
        print('FFmpeg downloaded successfully')


    def update_ffmpeg():
        global ffmpeg_version
        
        try:
            ver_str = subprocess.run(shlex.split('ffmpeg -version'), capture_output=True).stdout.splitlines()[0].decode()
            match = re.search(r'-([0-9]{8})', ver_str)
            ffmpeg_version = f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:]}" if match else "-"
        except Exception as e:
            print(e.with_traceback())
            ffmpeg_version = '-'


    def get_app_version():
        try:
            with open('version.txt', 'r') as f:
                return f.read()
        except:
            pass
        return '-'


    def get_ffmpeg_version():
        return ffmpeg_version


    def get_ytdlp_version():
        try:
            return yt_dlp.version.__version__ or '-'
        except:
            return '-'


    def downloader():
        print('Downloading yt-dlp and FFmpeg...')
        Downloader.download_ytdlp()
        time.sleep(random.random())
        if os.path.exists('lock'):
            while os.path.exists('lock'): time.sleep(1)
        else:
            open('lock', 'w').close()
            Downloader.download_ffmpeg()
            os.remove('lock')
        print('All downloads complete')
        Downloader.update_ffmpeg()
