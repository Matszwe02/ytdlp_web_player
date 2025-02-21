from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from urllib.parse import unquote
import os
import uuid
from datetime import datetime, timedelta
import time
from threading import Thread

from download_ytdlp import downloader as dwnl, yt_dlp
import requests
from hashlib import sha1


app = Flask(__name__)
DOWNLOAD_PATH = './download'
os.makedirs(DOWNLOAD_PATH, exist_ok=True)
os.environ['PATH'] = os.pathsep.join([os.getcwd(), os.environ['PATH']])
video_cache: dict[str, dict[str, str]] = {}


def get_ytdlp_version():
    try:
        return yt_dlp.version.__version__ or '-'
    except:
        return '-'


def downloader():
    dwnl()


immediate_downloader = Thread(target=downloader)



def gen_filename(url: str):
    return sha1(url.encode()).hexdigest()


def ytdlp_download():
    while True:
        time.sleep(86400) # 24 hours
        downloader()


def delete_old_files():
    while True:
        try:
            now = datetime.now()
            cutoff = now - timedelta(minutes=10)
            for filename in os.listdir(DOWNLOAD_PATH):
                file_path = os.path.join(DOWNLOAD_PATH, filename)
                if os.path.isfile(file_path):
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if file_time < cutoff:
                        os.remove(file_path)
                        print(f"Deleted old file: {file_path}")
            
            for i in list(video_cache.keys()).copy():
                if datetime.fromisoformat(video_cache[i]['timestamp']) < cutoff:
                    del video_cache[i]
        
        except: pass
        time.sleep(600)



def get_url(req):
    url = req.args.get('v') or req.args.get('url')
    if '.' not in url:
        url = 'https://youtube.com/watch?v=' + url
    return url



@app.route('/')
def index():
    return watch()


@app.route('/watch')
def watch():
    global immediate_downloader
    version = get_ytdlp_version()
    if len(version) <3:
        try:
            if not immediate_downloader.is_alive():
                immediate_downloader = Thread(target=downloader)
            immediate_downloader.start()
        finally:
            return ("YT-DLP is not present! Please wait as it will download", 500)
    return render_template('index.html', version=version)


@app.route('/search')
def search():
    url = get_url(request)
    
    if not url: return '', 404
    
    if url in video_cache.keys():
        print('Cache hit!')
        return video_cache[url]['file']
    
    ydl_opts = {"ffmpeg_location": "."}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    
    streaming_url = info.get('url', None)
    if streaming_url:

        # Check for media availability at streaming_url
        response = requests.head(streaming_url)
        if response.status_code == 200:
            video_cache[url] = {'file': streaming_url,'timestamp': datetime.now().isoformat()}
            return streaming_url
    
    unique_filename = str(uuid.uuid4())
    output_path = os.path.join('./download', unique_filename + '.%(ext)s')
    
    ydl_opts = {"outtmpl": f"{output_path}", "ffmpeg_location": "."}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download(unquote(url))
    
    for i in os.listdir(DOWNLOAD_PATH):
        if i.startswith(unique_filename):
            video_cache[url] = {'file': f'download/{i}','timestamp': datetime.now().isoformat()}
            return f'download/{i}'
    
    return 'Cannot gather video', 404



@app.route('/thumb')
def serve_thumbnail():
    url = get_url(request)
    filename = gen_filename(url)
    for path in os.listdir(DOWNLOAD_PATH):
        if filename in path and path.split('.')[1] in ['png', 'jpg', 'webp']:
            print('Thumbnail cache hit!')
            return send_from_directory(DOWNLOAD_PATH, path)
    
    ydl_opts = {"writethumbnail": True, "skip_download": True, "outtmpl": f"{os.path.join('./download', filename)}", "ffmpeg_location": "."}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download(unquote(url))
    
    for path in os.listdir(DOWNLOAD_PATH):
        if filename in path and path.split('.')[1] in ['png', 'jpg', 'webp']:
            print('Thumbnail cache hit!')
            return send_from_directory(DOWNLOAD_PATH, path)
    
    return '', 404



@app.route('/sb')
def get_sponsor_segments():
    """Return sponsor segments for a given YouTube video"""
    from flask import jsonify
    from sb import SponsorBlock
    
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



@app.route('/download/<path:filename>')
def download_ytdlp(filename):
    print(filename)
    print(os.path.join('download', filename))
    print(os.path.exists(os.path.join('download', filename)))
    return send_from_directory('download', filename)



if __name__ == '__main__':
    thread = Thread(target=delete_old_files)
    downloader_thread = Thread(target=ytdlp_download)
    thread.start()
    downloader_thread.start()
    app.run(threaded=True)
    # app.run()
