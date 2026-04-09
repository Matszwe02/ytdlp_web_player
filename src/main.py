import os
import time
import shutil
from threading import Thread
from source_downloader import Downloader
from dotenv import load_dotenv


load_dotenv()

app_title = os.environ.get('APP_TITLE', 'YT-DLP Player')
theme_color = os.environ.get('THEME_COLOR', '#ff7300')
generate_sprite_below = int(os.environ.get('GENERATE_SPRITE_BELOW', '1800'))
max_video_age = int(os.environ.get('MAX_VIDEO_AGE', '3600'))
max_video_duration = int(os.environ.get('MAX_VIDEO_DURATION', '36000'))
default_quality = int(os.environ.get('DEFAULT_QUALITY', '720'))
load_default_quality = (os.environ.get('LOAD_DEFAULT_QUALITY', 'True')).lower() == 'true'
cookies_only_on_failure = (os.environ.get('COOKIES_ONLY_ON_FAILURE', 'True')).lower() == 'true'
amoled_bg = os.environ.get('AMOLED_BG', 'False').lower() == 'true'
playlist_support = os.environ.get('PLAYLIST_SUPPORT', 'False').lower() == 'true'
auto_bg_playback = os.environ.get('AUTO_BG_PLAYBACK', 'False').lower() == 'true'
audio_visualizer = os.environ.get('AUDIO_VISUALIZER', 'False').lower() == 'true'
download_path = os.environ.get('DOWNLOAD_PATH', './download')
disable_transcoding = os.environ.get('DISABLE_TRANSCODING', 'False').lower() == 'true'


os.makedirs(download_path, exist_ok=True)
ffmpeg = shutil.which("ffmpeg")
if disable_transcoding:
    ffmpeg = None
    print("Running in no-transcoding mode. Resolution selection will not work, and some videos will fail to load!")
elif not ffmpeg:
    raise RuntimeError("FFMPEG can not be detected in your system. Install FFMPEG or disable transcoding.")

ydl_global_opts = {'ffmpeg-location': ffmpeg, "noplaylist": True, "remote_components": ["ejs:github"], "concurrent_fragment_downloads": 4}
if not shutil.which('deno'): ydl_global_opts["js_runtimes"] = {"node": {}}

app_version = Downloader.get_app_version()



def ytdlp_download():
    while True:
        Downloader.downloader()
        time.sleep(86400) # 24 hours


def delete_old_files():
    while True:
        try:
            for item_name in os.listdir(download_path):
                vid_path = os.path.join(download_path, item_name)

                keepalive_file = os.path.join(vid_path, 'keepalive')
                mtime = 0
                if os.path.exists(keepalive_file):
                    with open(keepalive_file, 'r') as f:
                        mtime = int(f.read())
                if time.time() - mtime > max_video_age:
                    print(f"Deleting old directory: {vid_path}")
                    shutil.rmtree(vid_path)

        except Exception as e:
            print(f"Error in delete_old_files: {e}")

        time.sleep(max_video_age / 2)



if __name__ == '__main__':
    Thread(target=delete_old_files, daemon=True).start()
    Thread(target=ytdlp_download, daemon=True).start()
    import uvicorn
    uvicorn.run("app:wsgi", host='0.0.0.0', port=5000, workers=8)
