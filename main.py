import threading
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify, send_file, Response
from urllib.parse import unquote, quote_plus, urlparse, parse_qs, urlencode, urlunparse
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
from dotenv import load_dotenv


load_dotenv()
app = Flask(__name__)
DOWNLOAD_PATH = './download'
os.makedirs(DOWNLOAD_PATH, exist_ok=True)
app_title = os.environ.get('APP_TITLE', 'YT-DLP Player')
theme_color = os.environ.get('THEME_COLOR', '#ff7300')
generate_sprite_below = int(os.environ.get('GENERATE_SPRITE_BELOW', '1800'))
amoled_bg = os.environ.get('AMOLED_BG', 'False').lower() == 'true'
ydl_global_opts = {'ffmpeg-location': shutil.which("ffmpeg")}



Downloader.get_app_version()
app_version = Downloader.get_app_version()



def gen_pathname(url: str):
    return sha1(url.encode()).hexdigest()


def get_data_dir(url):
    data_dir = os.path.join(DOWNLOAD_PATH, gen_pathname(url))
    return data_dir


def get_meta(url: str):
    with FileCachingLock(url, 'meta') as cache:
        print(cache)
        if cache:
            with open(cache, 'r') as f: return json.load(f)
        print(f'downloading meta for {url}')
        ydl_opts = {'quiet': True, 'skip_download': True}
        ydl_opts.update(ydl_global_opts)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.sanitize_info(ydl.extract_info(url, download=False))
            with open(os.path.join(get_data_dir(url), 'meta.json'), 'w') as f:
                json.dump(info, f)
                return info
    return None


def get_sb(url: str):
    with FileCachingLock(url, 'sb') as cache:
        try:
            print(cache)
            if cache:
                with open(cache, 'r') as f: return json.load(f)
            print(f'downloading sb for {url}')
            sb_data = SponsorBlock(url).get_segments()
            with open(os.path.join(get_data_dir(url), 'sb.json'), 'w') as f:
                json.dump(sb_data, f)
                return sb_data
        except:
            return None
    return None



def get_video_formats(url = None, meta = None):
    resolutions = []
    if not meta:
        meta = get_meta(url)
    formats = meta.get('formats', [])
    for f in formats:
        if f.get('vcodec') != 'none' and f.get('height') and f.get('height') not in resolutions:
            resolutions.append(f['height'])
    return resolutions



def get_video_sources(url):
    sources = {}
    best_audio = 0
    meta = get_meta(url)
    formats = meta.get('formats', [])
    for f in formats:
        video_name = f"{(f.get('height', ''))}" if f.get('vcodec', 'none').lower() != 'none' else ''
        audio_name = ''
        if f.get('acodec', 'none') != 'none':
            audio_name = 'audio_drc' if 'drc' in f"{f.get('format_id')} {f.get('format_note')}".lower() else 'audio'
        name = video_name + audio_name
        quality = float(f.get('quality') or 0)
        if not name: continue

        if name.startswith('audio') and quality < best_audio:
            best_audio = quality
            sources[name] = f['url']
        elif name not in sources:
            sources[name] = f['url']
    return sources



def get_subtitles(meta: dict):
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

    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)

    if 'list' in query_params:
        del query_params['list']

    new_query = urlencode(query_params, doseq=True)
    url = urlunparse(parsed_url._replace(query=new_query))

    if '.' not in url:
        url = 'https://youtube.com/watch?v=' + url
    return url


def download_media_file(url: str, path_without_ext: str, ext: str|None = None):
    """Download raw file with requests.get with selected filename"""
    response = requests.get(url, stream=True)
    response.raise_for_status()
    if not ext:
        urlpath = url
        if '?' in url:
            urlpath = url[:url.find('?')]
        _, ext = os.path.splitext(urlpath)
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
    response.headers.add('Content-Security-Policy', "frame-src *")
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
    print(f'Checking media for {url=} and {media_type=}')
    data_dir = get_data_dir(url)
    try:
        for i in os.listdir(data_dir):
            if i.endswith('.part'): continue
            if i.endswith('.temp'): continue
            if i.startswith(media_type):
                path = os.path.join(data_dir, i)
                print(f'Serving {path}')
                os.utime(path)
                print(f'Media for {url=} and {media_type=} found')
                return path
    except:
        return None
    return None


class FileCachingLock:
    def __init__(self, url, media_type):
        self.url = url
        self.media_type = media_type
        self.data_dir = get_data_dir(url)

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
        
        os.makedirs(self.data_dir, exist_ok=True)
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
    data_dir = get_data_dir(url)
    os.makedirs(data_dir, exist_ok=True)
    output_path = os.path.join(data_dir, f'{media_type}.%(ext)s')
    print(f'Downloading {media_type} for {url}')
    
    with FileCachingLock(url, media_type) as cache:
        if cache: return cache
        
        ydl_opts = {"outtmpl": output_path}
        ydl_opts.update(ydl_global_opts)
        
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
            download_media_file(thumb_url, os.path.join(data_dir, 'thumb_orig'))
            try:
                video_width = meta.get('width')
                video_height = meta.get('height')

                if video_width and video_height:
                    thumb_file = check_media(url=url, media_type='thumb_orig')

                    ffmpeg_command = [
                        'ffmpeg',
                        '-y',
                        '-i', thumb_file,
                        '-vf', f'crop=w=min(iw\\,ih*({video_width}/{video_height})):h=min(ih\\,iw*({video_height}/{video_width})):x=(iw-ow)/2:y=(ih-oh)/2',
                        thumb_file.replace('thumb_orig', 'thumb')
                    ]

                    subprocess.run(ffmpeg_command, check=True)
                    print(f"Thumbnail cropped to video aspect ratio {video_width}:{video_height} using ffmpeg")
                    os.remove(thumb_file)
                else:
                    print("Video dimensions not found in meta, skipping thumbnail cropping.")
                    shutil.move(thumb_file, thumb_file.replace('thumb_orig', 'thumb'))
            except Exception as e:
                print(f"Error cropping thumbnail: {e}")


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

        elif media_type.startswith('hls'):
            meta = get_meta(url)
            hls_url_dir = os.path.join(gen_pathname(url), f"playlist-{res}")
            hls_output_dir = os.path.join(DOWNLOAD_PATH, hls_url_dir)
            os.makedirs(hls_output_dir, exist_ok=True)

            temp_m3u8_path = os.path.join(data_dir, f'{media_type}.m3u8.temp')
            m3u8_path = os.path.join(data_dir, f'{media_type}.m3u8')
            hls_duration = 10
            res_str = str(res)

            sources = get_video_sources(url)
            video_url = None
            audio_url = None
            video_file_path = check_media(url=url, media_type='video-' + res_str)

            if not video_file_path:
                if res_str in sources:
                    if res_str == 'audio' or res_str == 'audio_drc':
                        audio_url = sources[res_str]
                    else:
                        video_url = sources[res_str]
                        audio_url = sources.get('audio_drc') or sources.get('audio') # Prefer audio_drc

                print(f'sources: {video_url}, {audio_url}')
                if not video_url and not audio_url:
                    print('Could not find any suitable streamable video format: Downloading the whole video')
                    video_file_path = download_file(url, f'video-{res}p')

            ffmpeg_command = [
                '-c:v', 'libx264',
                '-crf', '22',
                '-r', f'{meta.get("fps", "30")}',
                '-c:a', 'aac',
                '-ar', '44100',
                '-f', 'hls',
                '-force_key_frames', f'expr:gte(t,n_forced*{hls_duration})',
                '-hls_time', f'{hls_duration}',
                '-hls_playlist_type', 'vod',
                '-hls_segment_filename', os.path.join(hls_output_dir, 'segment%04d.ts'),
                temp_m3u8_path
            ]

            if video_url:
                ffmpeg_command = ['-i', video_url] + ffmpeg_command
            if audio_url:
                ffmpeg_command = ['-i', audio_url] + ffmpeg_command
            if video_file_path:
                ffmpeg_command = ['-i', video_file_path] + ffmpeg_command

            ffmpeg_command = ['ffmpeg'] + ffmpeg_command

            seg_time = 0
            seg_num = 0
            duration = meta["duration"]
            seg_path = f"/hls_stream/{hls_url_dir.rstrip('/')}/"

            with open(m3u8_path, "w") as f:
                f.write(f"#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:{hls_duration}\n#EXT-X-MEDIA-SEQUENCE:0\n#EXT-X-PLAYLIST-TYPE:VOD\n")
                while seg_time < duration:
                    time_to_add = min(hls_duration, meta["duration"] - seg_time)
                    f.write(f"#EXTINF:{time_to_add:.6f},\n{seg_path}segment{seg_num:0>4}.ts\n")
                    seg_time += time_to_add
                    seg_num += 1
                f.write("#EXT-X-ENDLIST\n")
            
            def download_hls_files():
                nonlocal video_file_path
                try:
                    proc = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    time.sleep(10)
                    if not video_file_path:
                        video_file_path = download_file(url, f'video-{res}p')
                        if not video_file_path: raise RuntimeError('Could not download video')
                        proc.kill()
                        os.rename(m3u8_path, temp_m3u8_path)
                        download_file(url, media_type)
                        return
                    if proc.wait() == 0:
                        with open(temp_m3u8_path, 'r') as f:
                            contents = f.read()
                        with open(m3u8_path, 'w') as f:
                            f.write(contents.replace('segment', seg_path + 'segment'))
                        os.remove(temp_m3u8_path)
                except Exception as e:
                    print(f"An unexpected error occurred during HLS conversion: {e}")

            Thread(target=download_hls_files).start()

            for _ in range(300):
                if os.path.exists(os.path.abspath(os.path.join(hls_output_dir, f'segment{min(2, seg_num):0>4}.ts'))): break
                time.sleep(0.1)


        elif media_type.startswith('sub'):
            lang = media_type.split('-')[1]
            print(f'downloading sub for {lang=}')
            meta = get_meta(url)

            sub = {**meta.get('subtitles', {}), **meta.get('automatic_captions', {})}.get(lang, '')
            for i in sub:
                if i.get('ext') == 'srt':
                    sub_url = i.get('url')
                    if sub_url:
                        download_media_file(sub_url, os.path.join(data_dir, media_type), 'srt')
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
            meta = get_meta(url)
            if get_meta(url)["duration"] > generate_sprite_below: raise ValueError(f"Video too long to generate sprite! ({get_meta(url)["duration"]}s)")
            if not meta.get('height') and not meta.get('width'): raise TypeError('Sprite not available on non-video media!')
            video_path = check_media(url=url, media_type='video')
            if not video_path:
                download_file(url, 'video')
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


        elif media_type.startswith('sources'):
            print(f'downloading sources for {url}')
            sources_data = get_video_sources(url)
            with open(os.path.join(data_dir, f'{media_type}.json'), 'w') as f:
                f.write(jsonify(sources_data).get_data(as_text=True))

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
    return render_template('index.html', ydl_version=ydl_version, app_version=app_version, ffmpeg_version=ffmpeg_version, app_title=app_title, theme_color=theme_color, amoled_bg=amoled_bg)



@app.route('/watch')
def watch():
    print('Started serving watch')
    ydl_version = Downloader.get_ytdlp_version()
    ffmpeg_version = Downloader.get_ffmpeg_version()
    original_url = get_url(request)
    
    video_width = 1280
    video_height = 720
    video_title = app_title

    meta_result = []
    meta_event = threading.Event()

    def get_meta_threaded():
        meta = get_meta(original_url)
        if meta:
            meta_result.append(meta)
        meta_event.set()

    meta_thread = Thread(target=get_meta_threaded)
    meta_thread.start()

    meta_event.wait(timeout=0.1)

    if meta_result:
        meta = meta_result[0]
        video_width = meta.get('width', video_width)
        video_height = meta.get('height', video_height)
        video_title = meta.get('title', app_title)
    else:
        dwnl1 = lambda: download_file(original_url, 'thumb')
        Thread(target=dwnl1).start()
        dwnl2 = lambda: get_meta(original_url)
        Thread(target=dwnl2).start()

    print('Stopped serving watch')
    return render_template('watch.html', original_url=original_url, ydl_version=ydl_version, app_version=app_version, ffmpeg_version=ffmpeg_version, app_title=app_title, theme_color=theme_color, generate_sprite_below=generate_sprite_below, amoled_bg=amoled_bg, video_width=video_width, video_height=video_height, video_title=video_title)



@app.route('/iframe')
def iframe():
    print('Started serving iframe')
    original_url = get_url(request)
    
    video_width = 1280
    video_height = 720

    meta_result = []
    meta_event = threading.Event()

    def get_meta_threaded():
        meta = get_meta(original_url)
        if meta:
            meta_result.append(meta)
        meta_event.set()

    meta_thread = Thread(target=get_meta_threaded)
    meta_thread.start()

    meta_event.wait(timeout=0.1)

    if meta_result:
        meta = meta_result[0]
        video_width = meta.get('width', video_width)
        video_height = meta.get('height', video_height)
    else:
        dwnl1 = lambda: download_file(original_url, 'thumb')
        Thread(target=dwnl1).start()
        dwnl2 = lambda: get_meta(original_url)
        Thread(target=dwnl2).start()

    print('Stopped serving iframe')
    return render_template('iframe.html', app_title=app_title, theme_color=theme_color, generate_sprite_below=generate_sprite_below, video_width=video_width, video_height=video_height)



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
    return get_sb(get_url(request)) or ("No sponsorblock data found for this video", 404)


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


@app.route('/low')
def download_low_quality():
    if filename:= check_media(get_url(request), 'video-low'):
        return send_from_directory(os.path.dirname(filename), os.path.basename(filename))
    formats = get_video_formats(get_url(request))
    filename = check_media(get_url(request), 'video')
    media_type = 'video'
    if not filename:
        media_type = f'video-{formats[0]}'
        filename = download_file(get_url(request), media_type)

    ffmpeg_command = [
        'ffmpeg',
        '-i', filename,
        '-c:v', 'libx264',
        '-crf', '38',
        '-c:a', 'aac',
        '-r', '30',
        '-preset', 'veryfast',
        os.path.join(get_data_dir(get_url(request)), 'video-low.mp4')
    ]
    try:
        proc = subprocess.run(ffmpeg_command, check=True, capture_output=True)
        proc.check_returncode()
    except Exception as e:
        print(f"An unexpected error occurred during conversion: {e}")
    return host_file(get_url(request), 'video-low')



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



@app.route('/sources')
def sources():
    return host_file(get_url(request), 'sources')


@app.route('/subtitle')
def serve_subtitle():
    return host_file(get_url(request), f'sub-{request.args.get("lang")}')


@app.route('/meta')
def serve_meta():
    meta = {}
    url = get_url(request)
    if not url: return jsonify({"error": "URL parameter is required"}), 400

    raw_meta = get_meta(url)
    meta['title'] = raw_meta.get('title', '')
    meta['uploader'] = raw_meta.get('uploader', '')
    try:
        meta['formats'] = get_video_formats(meta=raw_meta)
    except BaseException as e:
        meta['formats'] = jsonify({'error': (re.sub(r'[^\x20-\x7e]',r'', re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", str(e))))}), 403
    meta['duration'] = f'{raw_meta["duration"]}'
    meta['subtitles'] = get_subtitles(raw_meta)
    meta['width'] = raw_meta.get('width')
    meta['height'] = raw_meta.get('height')
    
    dwnl = lambda: download_file(url, 'thumb')
    Thread(target=dwnl).start()
    return meta


@app.route('/manifest.json')
def serve_manifest():
    return render_template('manifest.json', app_title=app_title, theme_color=theme_color, amoled_bg=amoled_bg)


@app.route('/hls')
def download_hls():
    res = (request.args.get('quality') or '').removesuffix("p")    
    media_type = 'hls' if res == 'audio' else f'hls-{res}p'.removesuffix('-p')
    return host_file(get_url(request), media_type)


@app.route('/hls_stream/<path:filename>')
def hls_stream(filename):
    base_dir = os.path.abspath(DOWNLOAD_PATH)
    full_path = os.path.abspath(os.path.join(base_dir, filename))

    if not full_path.startswith(base_dir):
        return jsonify({"error": "Invalid file path"}), 400

    if not os.path.exists(full_path):
        return jsonify({"error": "File not found"}), 404

    mime_type, _ = mimetypes.guess_type(full_path)
    if not mime_type:
        mime_type = 'application/octet-stream'

    return send_file_partial(full_path)


@app.route('/search')
def search():
    try:
        query = request.args.get('q')
        print(f'Searching for {query}')
        ydl_opts = {'quiet': True, 'skip_download': True, 'default_search': 'auto'}
        ydl_opts.update(ydl_global_opts)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.sanitize_info(ydl.extract_info(query, download=False))
            return info.get('entries', [{}])[0].get('original_url', '')
    except Exception as e:
        return (re.sub(r'[^\x20-\x7e]',r'', re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", str(e)))), 404
    return None



thread = Thread(target=delete_old_files)
downloader_thread = Thread(target=ytdlp_download)
thread.start()
downloader_thread.start()



if __name__ == '__main__':
    app.run(threaded=True, host='0.0.0.0')
