from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify, send_file, Response
from urllib.parse import unquote, quote_plus
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
import mimetypes
import json


app = Flask(__name__)
DOWNLOAD_PATH = './download'
os.makedirs(DOWNLOAD_PATH, exist_ok=True)
app_title = os.environ.get('APP_TITLE', 'YT-DLP Player')



Downloader.get_app_version()
app_version = Downloader.get_app_version()



def gen_pathname(url: str):
    return sha1(url.encode()).hexdigest()


def get_meta(url: str):
    with FileCachingLock(url, 'meta') as cache:
        print(cache)
        if cache:
            with open(cache, 'r') as f: return json.load(f)
        data_dir = os.path.join('./download', gen_pathname(url))
        print(f'downloading meta for {url}')
        ydl_opts = {'quiet': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.sanitize_info(ydl.extract_info(url, download=False))
            with open(os.path.join(data_dir, 'meta.json'), 'w') as f:
                json.dump(info, f)
                return info
    return None



def get_video_formats(url):
    resolutions = []
    meta = get_meta(url)
    formats = meta.get('formats', [])
    for f in formats:
        if f.get('vcodec') != 'none' and f.get('height') and f.get('height') not in resolutions:
            resolutions.append(f['height'])
    return resolutions



def get_video_sources(url):
    sources = {}
    meta = get_meta(url)
    formats = meta.get('formats', [])
    for f in formats:
        video_name = f"{(f.get('height', ''))}" if f.get('vcodec', 'none').lower() != 'none' else ''
        audio_name = ''
        if f.get('acodec', 'none') != 'none':
            audio_name = 'audio_drc' if 'drc' in f"{f.get('format_id')} {f.get('format_note')}".lower() else 'audio'
        name = video_name + audio_name

        if (video_name or audio_name) and name not in sources:
            sources[name] = f['url']
    return sources



def get_subtitles(url):
    meta = get_meta(url)
    subs = {**meta.get('subtitles', {}), **meta.get('automatic_captions', {})}
    all_subtitles = []
    for lang, subs in subs.items():
        if subs:
            all_subtitles.append(lang)
    return all_subtitles


def get_fastest_quality(url):
    meta = get_meta(url)
    formats = meta.get('formats', [])
    for f in formats:
        if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('protocol') == 'https':
            return f.get('url'), f.get('ext')
    return None, None


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


def download_media_file(url, path_without_ext, ext = None):
    """Download raw file with requests.get with selected filename"""
    response = requests.get(url, stream=True)
    response.raise_for_status()
    if not ext:
        _, ext = os.path.splitext(url)
    with open(f'{path_without_ext}.{ext.lstrip(".")}', 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)


def stream_media_file(url):
    """Stream raw file with requests.get"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, stream=True, headers=headers)
        response.raise_for_status()
        file_size = response.headers.get('content-length')
        mime_type = response.headers.get('content-type', 'application/octet-stream')

        def generate():
            for chunk in response.iter_content(chunk_size=8192):
                yield chunk

        resp = Response(generate(), mimetype=mime_type)
        if file_size:
            resp.headers['Content-Length'] = file_size
        resp.headers['Accept-Ranges'] = 'bytes'
        return resp
    except requests.exceptions.RequestException as e:
        print(f"Error streaming media file: {e}")
        return jsonify({"error": f"Failed to stream media: {e}"}), 500


@app.after_request
def after_request(response):
    response.headers.add('Accept-Ranges', 'bytes')
    return response


def send_file_partial(path):
    """ 
        Simple wrapper around send_file which handles HTTP 206 Partial Content
        (byte ranges)
        TODO: handle all send_file args, mirror send_file's error handling
        (if it has any)
    """
    range_header = request.headers.get('Range', None)
    if not range_header: return send_file(path)
    
    size = os.path.getsize(path)    
    byte1, byte2 = 0, None
    
    m = re.search(r'(\d+)-(\d*)', range_header)
    g = m.groups()
    
    if g[0]: byte1 = int(g[0])
    if g[1]: byte2 = int(g[1])

    length = size - byte1
    if byte2 is not None:
        length = byte2 - byte1
    
    data = None
    with open(path, 'rb') as f:
        f.seek(byte1)
        data = f.read(length)

    rv = Response(data, 
        206,
        mimetype=mimetypes.guess_type(path)[0], 
        direct_passthrough=True)
    rv.headers.add('Content-Range', 'bytes {0}-{1}/{2}'.format(byte1, byte1 + length - 1, size))

    return rv



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


class FileCachingLock:
    def __init__(self, url, media_type):
        self.url = url
        self.media_type = media_type
        self.data_dir = os.path.join('./download', gen_pathname(self.url))

    def __enter__(self):
        for _ in range(600):
            if not os.path.exists(os.path.join(self.data_dir, f'{self.media_type}.temp')):
                break
            time.sleep(1)
            print(f'Waiting for download of {self.media_type}')
        
        if cached_media := check_media(url=self.url, media_type=self.media_type):
            print(f'Cache hit for {self.media_type}!')
            self.url = None
            return cached_media
        
        with open(os.path.join(self.data_dir, f'{self.media_type}.temp'), 'w') as f:
            f.write(datetime.now().isoformat())
        
        return None

    def __exit__(self, exc_type, exc_value, traceback):
        if self.url:
            try: os.remove(os.path.join(self.data_dir, f'{self.media_type}.temp'))
            except: print(f'FATAL ERROR trying to unlock {self.media_type} of {self.data_dir}. Media type cannot be downloaded')



def download_file(url: str, media_type='video'):
    """
    media_type = video | thumb | audio | video-720p | video-720p_4.20-21.37 | video-best
    """
    url = re.sub(r'(https?):/{1,}', r'\1://', url)
    data_dir = os.path.join('./download', gen_pathname(url))
    os.makedirs(data_dir, exist_ok=True)
    output_path = os.path.join(data_dir, f'{media_type}.%(ext)s')
    print(f'Downloading {media_type} for {url}')
    
    with FileCachingLock(url, media_type) as cache:
        if cache: return cache
        
        ydl_opts = {"outtmpl": output_path, "ffmpeg_location": "."}
        
        timestamps = re.search(r'_(\d+\.?\d*)-(\d+\.?\d*)', media_type)
        default_res = '720p' if get_meta(url).get('duration', 0) < 300 else '240p'
        res = int((re.search(r'(\d+)p', media_type) and re.search(r'(\d+)p', media_type).group(1) or default_res).removesuffix('p'))
        
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
            meta = get_meta(url)
            thumb_url = meta['thumbnail']
            download_media_file(thumb_url, os.path.join(data_dir, 'thumb'))


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
            meta = get_meta(url)

            sub = {**meta.get('subtitles', {}), **meta.get('automatic_captions', {})}.get(lang, '')
            for i in sub:
                if i.get('ext') == 'srt':
                    sub_url = i.get('url')
                    if sub_url:
                        download_media_file(sub_url, os.path.join(data_dir, media_type))
                        break
            else:
                raise FileNotFoundError('Selected subtitles not found')
            
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
                time.sleep(60)
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


        elif media_type.startswith('sources'):
            print(f'downloading sources for {url}')
            sources_data = get_video_sources(url)
            with open(os.path.join(data_dir, f'{media_type}.json'), 'w') as f:
                f.write(jsonify(sources_data).get_data(as_text=True))


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

        return check_media(url=url, media_type=media_type)


def host_file(url: str, media_type='video'):
    if not url: return jsonify({"error": "URL parameter is required"}), 400
    file = download_file(url, media_type)
    if file:
        return send_file_partial(file)
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
    html_template = f'<video controls autoplay><source src="/download?url={get_url(request)}" type="video/mp4"></video>'
    return html_template



@app.route('/download')
def download_media():
    res = (request.args.get('quality') or '').removesuffix("p")
    start_time = request.args.get('start', 0, type=float)
    end_time = request.args.get('end', 0, type=float)
    
    media_type = 'audio' if res == 'audio' else f'video-{res}p'.removesuffix('-p')
    
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


@app.route('/fastest')
def resp_fastest_stream():
    url = get_url(request)
    fastest_url, _ = get_fastest_quality(url)
    if fastest_url:
        return stream_media_file(fastest_url)
    return download_media()


@app.route('/stream')
def stream_media():
    url = get_url(request)
    quality = request.args.get('quality')

    if not url or not quality:
        return jsonify({"error": "URL and quality parameters are required"}), 400

    sources = get_video_sources(url)
    video_url = None
    audio_url = None

    if quality in sources:
        if quality.endswith('audio') and not quality.startswith('audio'): # e.g., "1080audio"
            video_url = sources[quality]
            # Audio is combined, no separate audio needed
        elif quality == 'audio' or quality == 'audio_drc':
            audio_url = sources[quality]
            # Only audio, no video needed
        else: # Numeric video quality, e.g., "1080"
            video_url = sources[quality]
            audio_url = sources.get('audio_drc') or sources.get('audio') # Prefer audio_drc

    if not video_url and not audio_url:
        return jsonify({"error": f"No suitable format found for quality: {quality}"}), 404

    if video_url and audio_url:
        # Mux video and audio with FFmpeg
        command = [
            'ffmpeg',
            '-i', video_url,
            '-i', audio_url,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-f', 'mp4',
            '-movflags', 'frag_keyframe+empty_moov',
            'pipe:1'
        ]
        print(f"FFmpeg command: {' '.join(command)}")
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            def generate():
                while True:
                    chunk = process.stdout.read(8192)
                    if not chunk:
                        break
                    yield chunk
                process.stdout.close()
                process.wait()
                if process.returncode != 0:
                    print(f"FFmpeg error: {process.stderr.read().decode()}")

            return Response(generate(), mimetype='video/mp4')
        except Exception as e:
            print(f"Error muxing streams with FFmpeg: {e}")
            return jsonify({"error": f"Failed to mux streams: {e}"}), 500
    elif video_url:
        return stream_media_file(video_url)
    elif audio_url:
        return stream_media_file(audio_url)
    
    return jsonify({"error": "Unexpected error in stream_media"}), 500


@app.route('/formats')
def formats():
    return host_file(get_url(request), 'formats')


@app.route('/sources')
def sources():
    return host_file(get_url(request), 'sources')


@app.route('/subtitle')
def serve_subtitle():
    return host_file(get_url(request), f'sub-{request.args.get("lang")}')


@app.route('/subtitles')
def subtitles():
    return host_file(get_url(request), 'listsub')

@app.route('/manifest.json')
def serve_manifest():
    return render_template('manifest.json', app_title=app_title)



thread = Thread(target=delete_old_files)
downloader_thread = Thread(target=ytdlp_download)
thread.start()
downloader_thread.start()



if __name__ == '__main__':
    app.run(threaded=True)
