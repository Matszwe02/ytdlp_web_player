from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify
from urllib.parse import unquote
import os
import uuid
from datetime import datetime, timedelta
import time
import shutil
from threading import Thread
from sb import SponsorBlock
import re
from source_downloader import Downloader, yt_dlp
import requests
from hashlib import sha1


app = Flask(__name__)
DOWNLOAD_PATH = './download'
os.makedirs(DOWNLOAD_PATH, exist_ok=True)
app_title = os.environ.get('APP_TITLE', 'YT-DLP Player')



Downloader.get_app_version()
app_version = Downloader.get_app_version()



def gen_pathname(url: str):
    return sha1(url.encode()).hexdigest()



def ytdlp_download():
    while True:
        Downloader.downloader()
        time.sleep(86400) # 24 hours



def delete_old_files():
    max_file_age = 3600 # 1 hour
    while True:
        threshold = time.time() - max_file_age

        try:
            for item_name in os.listdir(DOWNLOAD_PATH):
                item_path = os.path.join(DOWNLOAD_PATH, item_name)

                if os.path.isdir(item_path):
                    try:
                        files = [f for f in os.listdir(item_path) if os.path.isfile(os.path.join(item_path, f))]

                        for filename in files:
                            if os.path.getmtime(os.path.join(item_path, filename)) >= threshold:
                                break

                        else:
                            print(f"Deleting old directory: {item_path}")
                            shutil.rmtree(item_path)

                    except OSError as e:
                        print(f"Error processing directory {item_path}: {e}")

        except Exception as e:
            print(f"Error in delete_old_files: {e}")

        time.sleep(max_file_age / 2)



def get_url(req):
    url = req.args.get('v') or req.args.get('url') or None
    if url is None: return None
    if '.' not in url:
        url = 'https://youtube.com/watch?v=' + url
    return url



def check_media(url: str, media_type: str):
    unique_path = gen_pathname(url)
    data_dir = os.path.join('./download', unique_path)
    try:
        for i in os.listdir(data_dir):
            if i.startswith(media_type):
                path = os.path.join(data_dir, i)
                print(f'Serving {path}')
                os.utime(path)
                return path
    except:
        return None
    return None



def download_file(url: str, media_type='video'):
    """
    media_type = video | thumb | audio | video-720p
    """
    print(f'Downloading {media_type} for {url}')
    if i := check_media(url=url, media_type=media_type):
        print(f'Cache hit for {media_type}!')
        return i
    
    data_dir = os.path.join('./download', gen_pathname(url))
    os.makedirs(data_dir, exist_ok=True)
    output_path = os.path.join(data_dir, f'{media_type}.%(ext)s')
    
    
    def dwnl(url, ydl_opts):
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f'YTDLP: downloading "{unquote(url)}"')
            ydl.download(unquote(url))
    
    
    if media_type == 'thumb':
        dwnl(url, {"writethumbnail": True, "skip_download": True, "outtmpl": f"{output_path}", "ffmpeg_location": "."})
    
    
    if media_type.startswith('video'):
        res = int(re.search(r'(\d+)p', media_type) and re.search(r'(\d+)p', media_type).group(1) or 720)
        video_format = f"bestvideo[height<={res}][ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        
        print(f'{video_format=}')
        
        try:
            dwnl(url, {"outtmpl": output_path, "ffmpeg_location": ".", "format": video_format})
        
        except yt_dlp.utils.DownloadError:
            dwnl(url, {"outtmpl": f"{output_path}", "ffmpeg_location": ".", "format": "best"})
            print('Unavailable format: using default format')
    
    return check_media(url=url, media_type=media_type)



@app.route('/')
def index():
    ydl_version = Downloader.get_ytdlp_version()
    ffmpeg_version = Downloader.get_ffmpeg_version()
    return render_template('index.html', ydl_version=ydl_version, app_version=app_version, ffmpeg_version=ffmpeg_version, app_title=app_title)



@app.route('/watch')
def watch():
    ydl_version = Downloader.get_ytdlp_version()
    ffmpeg_version = Downloader.get_ffmpeg_version()
    original_url = get_url(request)
    return render_template('watch.html', original_url=original_url, ydl_version=ydl_version, app_version=app_version, ffmpeg_version=ffmpeg_version, app_title=app_title)



@app.route('/search')
def search():
    url = get_url(request)
    if not url: return 'url param empty', 404
    
    filename = download_file(url, 'video-720p')
    
    if filename: return filename
    return 'Cannot gather video', 404



@app.route('/thumb')
def serve_thumbnail():
    url = get_url(request)
    if not url: return 'url param empty', 404
    
    filename = download_file(url, 'thumb')
    
    if filename: return send_from_directory(directory=os.path.dirname(filename), path=os.path.basename(filename))
    return 'Cannot gather thumbnail', 404



@app.route('/sb')
def get_sponsor_segments():
    """Return sponsor segments for a given YouTube video"""
    
    # Get video ID from request parameters
    url = get_url(request)
    if not url:
        return jsonify({"error": "Video ID is required"}), 400
        
    try:
        # Create SponsorBlock instance and get segments
        sb = SponsorBlock(url)
        segments = sb.get_segments()
        
        return jsonify(segments)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/raw')
def raw():
    url = search()
    html_template = f'<video controls autoplay><source src="{url}" type="video/mp4"></video>'
    return html_template



@app.route('/download')
def download_media():
    
    url = get_url(request)
    if not url: return 'url param empty', 404
    
    res = request.args.get('quality') or '720'
    filename = download_file(url, f'video-{res.removesuffix("p")}p')
    
    if filename: return send_from_directory(directory=os.path.dirname(filename), path=os.path.basename(filename))
    return 'Cannot gather video', 404



@app.route('/download/<path:filename>')
def download_ytdlp(filename):
    print(filename)
    serve_path = (os.path.join('download', filename))
    os.utime(os.path.join(serve_path))
    return send_from_directory(os.path.dirname(serve_path), os.path.basename(serve_path))



thread = Thread(target=delete_old_files)
downloader_thread = Thread(target=ytdlp_download)
thread.start()
downloader_thread.start()



if __name__ == '__main__':
    app.run(threaded=True)
    # app.run(threaded=False)
