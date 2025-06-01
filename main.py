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



def get_video_formats(url):
    resolutions = []
    ydl_opts = {'quiet': True, 'skip_download': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        formats = info_dict.get('formats', [])
        
        for f in formats:
            if f.get('vcodec') != 'none' and f.get('height') and f.get('height') not in resolutions:
                resolutions.append(f['height'])
    
    return resolutions



@app.route('/formats')
def formats():
    url = get_url(request)
    if not url:
        return jsonify({"error": "URL parameter ('v' or 'url') is required"}), 400
    
    video_formats = get_video_formats(url)
    return jsonify(video_formats)



def get_subtitles(url):
    ydl_opts = {'quiet': True, 'skip_download': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        subtitles = info_dict.get('subtitles', {})
        automatic_captions = info_dict.get('automatic_captions', {})
        
        all_subtitles = []
        
        for lang, subs in subtitles.items():
            if subs:
                all_subtitles.append(lang)
        
        for lang, subs in automatic_captions.items():
            if lang not in all_subtitles and subs:
                all_subtitles.append(lang)
        
        return all_subtitles



@app.route('/subtitles')
def subtitles():
    url = get_url(request)
    if not url:
        return jsonify({"error": "URL parameter ('v' or 'url') is required"}), 400
    
    subtitles = get_subtitles(url)
    return jsonify(subtitles)



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
            if i.endswith('.part'): continue
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
    media_type = video | thumb | audio | video-720p | video-720p_4.20-21.37 | video-best
    """
    url = re.sub(r'(https?):/{1,}', r'\1://', url)
    print(f'Downloading {media_type} for {url}')
    
    if i := check_media(url=url, media_type=media_type):
        print(f'Cache hit for {media_type}!')
        return i
    
    data_dir = os.path.join('./download', gen_pathname(url))
    os.makedirs(data_dir, exist_ok=True)
    output_path = os.path.join(data_dir, f'{media_type}.%(ext)s')
    
    ydl_opts = {"outtmpl": output_path, "ffmpeg_location": "."}
    
    timestamps = re.search(r'_(\d+\.?\d*)-(\d+\.?\d*)', media_type)
    res = int((re.search(r'(\d+)p', media_type) and re.search(r'(\d+)p', media_type).group(1) or '720p').removesuffix('p'))
    
    if timestamps:
        try:
            start_time = float(timestamps.group(1))
            end_time = float(timestamps.group(2))
            ydl_opts.update({'download_ranges': yt_dlp.utils.download_range_func(None, [(start_time, end_time)]), 'force_keyframes_at_cuts': True})
            print(f"Downloading section {start_time}-{end_time}")
        except ValueError:
            print("Error parsing start/end times from media_type")
    
    
    def dwnl(url, ydl_opts):
        print(f'YTDLP: downloading "{unquote(url)}" with options "{ydl_opts}"')
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download(unquote(url))
    
    
    if media_type == 'thumb':
        ydl_opts.update({"writethumbnail": True, "skip_download": True})
        dwnl(url, ydl_opts)
    
    
    elif media_type.startswith('audio'):
        ydl_opts.update({"format": "bestaudio/best", "extract_audio": True, "outtmpl": os.path.join(data_dir, f'{media_type}.mp3')})
        dwnl(url, ydl_opts)
    
    
    elif media_type.startswith('video'):
        download_best = media_type.startswith('video-best')
        if not download_best:
            print(f"Downloading quality {res}p")
            try:
                ydl_opts.update({"format": f"bestvideo[height<={res}][ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best"})
                dwnl(url, ydl_opts)
            except yt_dlp.utils.DownloadError:
                download_best = True
                formats = get_video_formats(url)
                print(f'WARNING: Counld not download selected format. Available formats:\n{formats}')
        
        if download_best:
            print("Downloading best quality")
            ydl_opts.update({"format": "best"})
            dwnl(url, ydl_opts)
    
    elif media_type.startswith('sub'):
        lang = media_type.split('-')[1]
        print(f'downloading sub for {lang=}')
        ydl_opts.update({
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': [lang],
            'subtitlesformat': 'srt',
            'outtmpl': os.path.join(data_dir, f'{media_type}.%(ext)s'),
        })
        dwnl(url, ydl_opts)
    
    return check_media(url=url, media_type=media_type)



@app.route('/')
def index():
    print('Started serving root')
    ydl_version = Downloader.get_ytdlp_version()
    ffmpeg_version = Downloader.get_ffmpeg_version()
    print('Stopped serving root')
    return render_template('index.html', ydl_version=ydl_version, app_version=app_version, ffmpeg_version=ffmpeg_version, app_title=app_title)



@app.route('/watch')
def watch():
    print('Started serving watch')
    ydl_version = Downloader.get_ytdlp_version()
    ffmpeg_version = Downloader.get_ffmpeg_version()
    original_url = get_url(request)
    print('Stopped serving watch')
    return render_template('watch.html', original_url=original_url, ydl_version=ydl_version, app_version=app_version, ffmpeg_version=ffmpeg_version, app_title=app_title)



@app.route('/search')
def search():
    print('Started serving search')
    url = get_url(request)
    if not url: return 'url param empty', 404
    
    filename = download_file(url, 'video-720p')
    
    print('Stopped serving search')
    if filename: return filename
    return 'Cannot gather video', 404



@app.route('/thumb')
def serve_thumbnail():
    url = get_url(request)
    return serve_thumbnail_by_path(url)



@app.route('/thumb/<path:url>')
def serve_thumbnail_by_path(url):
    print('Started serving thumb')
    if not url: return 'url param empty', 404
    
    filename = download_file(url, 'thumb')
    
    print('Stopped serving thumb')
    if filename: return send_from_directory(directory=os.path.dirname(filename), path=os.path.basename(filename))
    return 'Cannot gather thumbnail', 404



@app.route('/sb')
def get_sponsor_segments():
    """Return sponsor segments for a given YouTube video"""
    
    print('Started serving sb')
    # Get video ID from request parameters
    url = get_url(request)
    if not url:
        return jsonify({"error": "Video ID is required"}), 400
        
    try:
        # Create SponsorBlock instance and get segments
        sb = SponsorBlock(url)
        segments = sb.get_segments()
        
        print('Stopped serving sb')
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
    
    print('Started serving download')
    url = get_url(request)
    if not url: return 'url param empty', 404
    
    res = (request.args.get('quality') or '720').removesuffix("p")
    start_time = request.args.get('start', 0, type=float)
    end_time = request.args.get('end', 0, type=float)
    
    media_type = 'audio' if res == 'audio' else f'video-{res}p'
    
    if start_time > 0 or end_time > 0:
        media_type += f'_{start_time:.1f}-{end_time:.1f}'

    filename = download_file(url, media_type)
    
    print('Stopped serving download')
    if filename: return send_from_directory(directory=os.path.dirname(filename), path=os.path.basename(filename))
    return 'Cannot gather video', 404



@app.route('/download/<path:filename>')
def download_ytdlp(filename):
    print('Started serving download/path')
    print(filename)
    path = (os.path.join('download', filename))
    print(f'Serving {path}')
    os.utime(path)
    print('Stopped serving download/path')
    return send_from_directory(os.path.dirname(path), os.path.basename(path))



thread = Thread(target=delete_old_files)
downloader_thread = Thread(target=ytdlp_download)
thread.start()
downloader_thread.start()



@app.route('/subtitle')
def serve_subtitle():
    print('Started serving subtitle')
    url = get_url(request)
    lang = request.args.get('lang')
    
    if not url or not lang:
        return jsonify({"error": "URL parameter ('v' or 'url') and 'lang' parameter are required"}), 400
    
    path = download_file(url, f'sub-{lang}')
    print('Stopped serving subtitle')
    return send_from_directory(os.path.dirname(path), os.path.basename(path))



if __name__ == '__main__':
    app.run(threaded=True)
