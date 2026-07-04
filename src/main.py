import os
import time
import shutil
import subprocess
from threading import Thread
from external import External
from dotenv import load_dotenv


load_dotenv()

app_title = os.environ.get('APP_TITLE', 'YT-DLP Player')
theme_color = os.environ.get('THEME_COLOR', '#ff7300')
generate_sprite_below = int(os.environ.get('GENERATE_SPRITE_BELOW', '1800'))
max_video_age = int(os.environ.get('MAX_VIDEO_AGE', '3600'))
max_video_duration = int(os.environ.get('MAX_VIDEO_DURATION', '36000'))
default_quality = int(os.environ.get('DEFAULT_QUALITY', '720'))
max_quality = int(os.environ.get('MAX_QUALITY', '2160'))
always_transcode = (os.environ.get('ALWAYS_TRANSCODE', 'False')).lower() == 'true'
autoskip_sb_segments = [seg for seg in (os.environ.get('AUTOSKIP_SB_SEGMENTS') or '').split(',') if seg != '']
cookies_only_on_failure = (os.environ.get('COOKIES_ONLY_ON_FAILURE', 'True')).lower() == 'true'
amoled_bg = os.environ.get('AMOLED_BG', 'False').lower() == 'true'
playlist_support = os.environ.get('PLAYLIST_SUPPORT', 'True').lower() == 'true'
auto_bg_playback = os.environ.get('AUTO_BG_PLAYBACK', 'True').lower() == 'true'
audio_visualizer = os.environ.get('AUDIO_VISUALIZER', 'False').lower() == 'true'
download_path = os.environ.get('DOWNLOAD_PATH', './download')
disable_transcoding = os.environ.get('DISABLE_TRANSCODING', 'False').lower() == 'true'
proxy = os.environ.get('PROXY', '')
port = int(os.environ.get('PORT', '5000'))

hls_duration = 5
hls_audio_duration = 10


os.makedirs(download_path, exist_ok=True)
ffmpeg = shutil.which("ffmpeg")
if disable_transcoding:
    ffmpeg = None
elif not ffmpeg:
    ffmpeg = External.download_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("FFMPEG can not be detected nor installed in your system. Install FFMPEG or disable transcoding.")

js_runtime = shutil.which('node') or shutil.which('deno') or External.download_deno()

ydl_global_opts = {'ffmpeg-location': ffmpeg, "noplaylist": True, 'playlistend': 0, "remote_components": ["ejs:github"], "concurrent_fragment_downloads": 2}
if js_runtime and 'deno' not in subprocess.check_output([js_runtime, '--version']).decode(): ydl_global_opts["js_runtimes"] = {"node": {}}

app_version = External.get_app_version()
proxies = {proxy.split('://')[0]: proxy} if proxy else None



def ytdlp_download():
    while True:
        print(f"Running periodic yt-dlp update")
        External.download_ytdlp()
        time.sleep(86400) # 24 hours


def delete_old_files():
    while True:
        print(f"Running periodic removal of old files")
        try:
            for item_name in os.listdir(download_path):
                vid_path = os.path.join(download_path, item_name)
                if not os.path.isdir(vid_path): continue

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

    for item_name in os.listdir(download_path):
        item = os.path.join(download_path, item_name)
        if not os.path.isdir(item): os.remove(item)

    Thread(target=delete_old_files, daemon=True).start()
    Thread(target=ytdlp_download, daemon=True).start()
    import uvicorn
    uvicorn.run("app:wsgi", host='0.0.0.0', port=port, workers=4)
