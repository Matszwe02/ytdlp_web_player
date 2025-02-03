import os
import platform
import requests
import tarfile
import zipfile
import io
import shutil
import stat


YT_DLP = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux"
YT_DLP_ARM = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux_armv7l"
YT_DLP_ARM64 = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux_aarch64"
YT_DLP_WIN = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"

FFMPEG = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"
FFMPEG_ARM64 = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linuxarm64-gpl.tar.xz"
FFMPEG_WIN = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"


def download_ytdlp():
    if os.path.exists('yt-dlp'):
        os.remove('yt-dlp')
    if os.path.exists('yt-dlp.exe'):
        os.remove('yt-dlp.exe')
        
    print('Downloading yt-dlp...')
    if platform.system() == 'Windows':
        url = YT_DLP_WIN
    else:
        if platform.machine() == 'armv7l':
            url = YT_DLP_ARM
        elif platform.machine() == 'aarch64' or platform.machine() == 'arm64':
            url = YT_DLP_ARM64
        else:
            url = YT_DLP
    
    response = requests.get(url)
    with open('yt-dlp', 'wb') as f:
        f.write(response.content)
    print('yt-dlp downloaded successfully')

    if platform.system() == 'Windows':
        pass
    else:
        if not os.access('yt-dlp', os.X_OK):
            print('Making yt-dlp executable...')
            os.chmod('yt-dlp', 0o755)
            print('yt-dlp is now executable')
        else:
            print('yt-dlp is already executable')



def download_ffmpeg():
    if os.path.exists('ffmpeg'):
        os.remove('ffmpeg')
    if os.path.exists('ffprobe'):
        os.remove('ffprobe')
        
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
                        pass
                    else:
                        if not os.access(dst, os.X_OK):
                            print(f'Making {dst} executable...')
                            os.chmod(dst, 0o755)
                            print(f'{dst} is now executable')
                        else:
                            print(f'{dst} is already executable')

    shutil.rmtree('temp')
    
    print('FFmpeg downloaded successfully')


def downloader():
    print('Downloading yt-dlp and FFmpeg...')
    download_ytdlp()
    download_ffmpeg()
    print('All downloads complete')