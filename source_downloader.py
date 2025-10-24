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



ffmpeg_version = '-'

class Downloader:

    @staticmethod
    def download_ytdlp():
        global yt_dlp
        pip.main(shlex.split('install --upgrade yt-dlp'))
        try:
            importlib.reload(yt_dlp)
            importlib.reload(yt_dlp.version)
        except:
            import yt_dlp
            import yt_dlp.version


    @staticmethod
    def get_ffmpeg_version():
        global ffmpeg_version
        if ffmpeg_version != '-': return ffmpeg_version
        try:
            ffmpeg_path = shutil.which('ffmpeg')
            print(f'{ffmpeg_path=}')
            ver_str = subprocess.run(shlex.split(f'{ffmpeg_path} -version'), capture_output=True).stdout.splitlines()[0].decode()
            print(f'{ver_str=}')
            version = ver_str.split("sion")[-1].split("Copyright")[0]
            # match = re.search(r'-([0-9]{8})', ver_str)
            ffmpeg_version = f"{version}" if version else "-"
            print(ffmpeg_version)
        except Exception as e:
            print(e)
            ffmpeg_version = '-'
        return ffmpeg_version


    @staticmethod
    def get_app_version():
        try:
            with open('version.txt', 'r') as f:
                return f.read()
        except:
            pass
        return '-'


    @staticmethod
    def get_ytdlp_version():
        try:
            return yt_dlp.version.__version__ or '-'
        except:
            return '-'


    @staticmethod
    def downloader():
        print('Downloading yt-dlp...')
        Downloader.download_ytdlp()
