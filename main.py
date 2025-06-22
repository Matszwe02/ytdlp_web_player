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
import subprocess
from PIL import Image
import math


app = Flask(__name__)
DOWNLOAD_PATH = './download'
os.makedirs(DOWNLOAD_PATH, exist_ok=True)
app_title = os.environ.get('APP_TITLE', 'YT-DLP Player')



Downloader.get_app_version()
app_version = Downloader.get_app_version()



def gen_pathname(url: str):
    return sha1(url.encode()).hexdigest()



def get_video_duration(file_path):
    command = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        file_path
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"Error getting video duration for {file_path}: {e}")
        return None



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
            if i.endswith('.temp'): continue
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
    data_dir = os.path.join('./download', gen_pathname(url))
    os.makedirs(data_dir, exist_ok=True)
    output_path = os.path.join(data_dir, f'{media_type}.%(ext)s')
    print(f'Downloading {media_type} for {url}')
    
    if cached_media := check_media(url=url, media_type=media_type):
        print(f'Cache hit for {media_type}!')
        return cached_media
    
    for _ in range(3600):
        if not os.path.exists(os.path.join(data_dir, f'{media_type}.temp')):
            break
        time.sleep(1)
        print(f'Waiting for download of {media_type}')
    
    try:
        with open(os.path.join(data_dir, f'{media_type}.temp'), 'w') as f:
            f.write(datetime.now().isoformat())
        
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
                    ydl_opts.update({"format": f"bestvideo[height<={res}]+bestaudio/best"})
                    dwnl(url, ydl_opts)
                except Exception:
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
            file = check_media(url=url, media_type=media_type)
            if file:
                with open(file, 'r') as f:
                    data = f.read()
                data = re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})', r'\1.\2', data)
                with open(file, 'w') as f:
                    f.write('WEBVTT\n' + data)


        elif media_type.startswith('sprite'):
            video_path = check_media(url=url, media_type='video')
            if video_path:
                
                frame_interval = 10 # seconds
                frame_width = 160
                frame_height = 90
                frames_per_row = 10

                ffmpeg_command = [
                    'ffmpeg',
                    '-i', video_path,
                    '-vf', f'fps={1/frame_interval},scale={frame_width}:{frame_height}',
                    os.path.join(data_dir, 'frame_%04d.jpg')
                ]

                try:
                    subprocess.run(ffmpeg_command, check=True)
                    # Create sprite image
                    frame_files = sorted([f for f in os.listdir(data_dir) if f.startswith('frame')])
                    num_frames = len(frame_files)
                    num_rows = math.ceil(num_frames / frames_per_row)
                    canvas_width = frames_per_row * frame_width
                    canvas_height = num_rows * frame_height
                    print(f'Sprite: generated {num_frames} frames. Combining into a {canvas_width}x{canvas_height} sprite.')

                    sprite_image = Image.new('RGB', (canvas_width, canvas_height))

                    for i, frame_file in enumerate(frame_files):
                        frame_path = os.path.join(data_dir, frame_file)
                        with Image.open(frame_path) as img:
                            row = i // frames_per_row
                            col = i % frames_per_row
                            x = col * frame_width
                            y = row * frame_height
                            sprite_image.paste(img, (x, y))
                        os.remove(frame_path) # Clean up individual frames
                    sprite_image.save(os.path.join(data_dir, 'sprite.jpg'))
                except Exception as e:
                    print(f"Sprite error: {e}")


        elif media_type.startswith('formats'):
            print(f'downloading formats for {url}')
            formats_data = get_video_formats(url)
            with open(os.path.join(data_dir, f'{media_type}.json'), 'w') as f:
                f.write(jsonify(formats_data).get_data(as_text=True))


        elif media_type.startswith('listsub'):
            print(f'downloading subtitles for {url}')
            subtitles_data = get_subtitles(url)
            with open(os.path.join(data_dir, f'{media_type}.json'), 'w') as f:
                f.write(jsonify(subtitles_data).get_data(as_text=True))


        elif media_type.startswith('sb'):
            print(f'downloading sb for {url}')
            sb_data = SponsorBlock(url).get_segments()
            with open(os.path.join(data_dir, f'{media_type}.json'), 'w') as f:
                f.write(jsonify(sb_data).get_data(as_text=True))


        try: os.remove(os.path.join(data_dir, f'{media_type}.temp'))
        except: pass
        return check_media(url=url, media_type=media_type)
    except Exception as e:
        print(f'Exception during download of {media_type}: {e}')
        os.remove(os.path.join(data_dir, f'{media_type}.temp'))
        return None


def host_file(url: str, media_type='video'):
    if not url: return jsonify({"error": "URL parameter is required"}), 400
    file = download_file(url, media_type)
    if file:
        return send_from_directory(os.path.dirname(file), os.path.basename(file))
    return jsonify({"error": f"Cannot gather {media_type}"}), 404



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
    return download_file(get_url(request), 'video-720p')


@app.route('/thumb')
def serve_thumbnail():
    url = get_url(request)
    return serve_thumbnail_by_path(url)



@app.route('/thumb/<path:url>')
def serve_thumbnail_by_path(url):
    return host_file(url, 'thumb')


@app.route('/sprite')
def serve_sprite():
    url = get_url(request)
    return serve_sprite_by_path(url)


@app.route('/sprite/<path:url>')
def serve_sprite_by_path(url):

    return host_file(url, 'sprite')


@app.route('/sb')
def get_sponsor_segments():
    return host_file(get_url(request), 'sb')


@app.route('/raw')
def raw():
    url = search()
    html_template = f'<video controls autoplay><source src="{url}" type="video/mp4"></video>'
    return html_template



@app.route('/download')
def download_media():
    res = (request.args.get('quality') or '720').removesuffix("p")
    start_time = request.args.get('start', 0, type=float)
    end_time = request.args.get('end', 0, type=float)
    
    media_type = 'audio' if res == 'audio' else f'video-{res}p'
    
    if start_time > 0 or end_time > 0:
        media_type += f'_{start_time:.1f}-{end_time:.1f}'

    return host_file(get_url(request), media_type)



@app.route('/download/<path:filename>')
def download_ytdlp(filename):
    print('Started serving download/path')
    print(filename)
    path = (os.path.join('download', filename))
    print(f'Serving {path}')
    os.utime(path)
    print('Stopped serving download/path')
    return send_from_directory(os.path.dirname(path), os.path.basename(path))


@app.route('/formats')
def formats():
    return host_file(get_url(request), 'formats')


@app.route('/subtitle')
def serve_subtitle():
    return host_file(get_url(request), f'sub-{request.args.get("lang")}')


@app.route('/subtitles')
def subtitles():
    return host_file(get_url(request), 'listsub')



thread = Thread(target=delete_old_files)
downloader_thread = Thread(target=ytdlp_download)
thread.start()
downloader_thread.start()



if __name__ == '__main__':
    app.run(threaded=True)
