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
try:
    import yt_dlp.version
except:
    print('Warning: ytdlp does not support version')


ffmpeg_version = '-'

class Downloader:

    @staticmethod
    def download_ytdlp():
        global yt_dlp
        pip.main(shlex.split('install --upgrade yt-dlp'))
        try:
            importlib.reload(yt_dlp)
            try:
                importlib.reload(yt_dlp.version)
            except:
                print('Warning: ytdlp does not support version')
        except:
            import yt_dlp
            try:
                import yt_dlp.version
            except:
                print('Warning: ytdlp does not support version')


    @staticmethod
    def get_ffmpeg_version(ffmpeg_path):
        global ffmpeg_version
        if ffmpeg_version != '-': return ffmpeg_version
        try:
            ver_str = subprocess.run([ffmpeg_path, '-version'], capture_output=True).stdout.splitlines()[0].decode()
            ffmpeg_version = ver_str.split("sion")[-1].split("Copyright")[0] or '-'
        except Exception:
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
