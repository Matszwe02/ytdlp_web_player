import pip
import shlex
import importlib
import os
import platform
import requests
import zipfile, tarfile
import shutil
import io



FFMPEG = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"
FFMPEG_ARM64 = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linuxarm64-gpl.tar.xz"
FFMPEG_WIN = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"



def download_ytdlp():
    global yt_dlp
    pip.main(shlex.split('install --upgrade yt-dlp'))
    try:
        importlib.reload(yt_dlp)
        importlib.reload(yt_dlp.version)
    except NameError:
        import yt_dlp
        import yt_dlp.version



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


download_ytdlp()
if __name__ == '__main__':
    download_ffmpeg()