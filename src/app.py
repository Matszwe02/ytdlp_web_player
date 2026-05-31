from main import *
from flask import Flask, render_template, request, jsonify, send_file, Response
from urllib.parse import quote_plus, urlparse, parse_qs
import os
import time
import shutil
from threading import Thread
import re
from external import External, yt_dlp
import requests
from PIL import Image
import math
import mimetypes
import json
from starlette.middleware.wsgi import WSGIMiddleware
from addons import *


app = Flask(__name__)
wsgi = WSGIMiddleware(app)



def download_media_file(url: str, path_without_ext: str, ext: str|None = None):
    """Download raw file with requests.get with selected filename"""
    proxies = {proxy.split('://')[0]: proxy} if proxy else None
    response = requests.get(url, stream=True, proxies=proxies)
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


def send_file_partial(path, download_name: str | None = None):
    """ 
        Simple wrapper around send_file which handles HTTP 206 Partial Content
        (byte ranges)
        TODO: handle all send_file args, mirror send_file's error handling
        (if it has any)
    """
    range_header = request.headers.get('Range')
    if not range_header: return send_file(path, download_name=download_name)
    
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


def preload(url = None, meta = None, playlist = None):
    url = url or (meta.get('original_url') or '')
    print('Running preload')

    if meta:
        try:
            os.makedirs(get_data_dir(url), exist_ok=True)
            with open(os.path.join(get_data_dir(url), 'meta.json'), 'w') as f:
                json.dump(meta, f)
        except:
            pass

    if not check_media(url, 'meta'):
        Thread(target=get_meta, args=[url]).start()
    if not check_media(url, 'thumb'):
        Thread(target=MediaDownloader(url, 'thumb').run).start()
    if not check_media(url, 'hls-audio'):
        Thread(target=MediaDownloader(url, 'hls-audio').run).start()
    if playlist and not check_media(url, 'playlist'):
        with open(os.path.join(get_data_dir(url), 'playlist.json'), 'w') as f:
            json.dump(playlist, f)


class MediaDownloader:
    def __init__(self, url: str, media_type: str):
        self.url = re.sub(r'(https?):/{1,}', r'\1://', url)
        self.data_dir = get_data_dir(self.url)
        self.media_type = media_type
        os.makedirs(self.data_dir, exist_ok=True)


    def run(self):
        with FileCachingLock(self.url, self.media_type) as cache:
            if cache: return cache
            self._load_variables()
            if   self.media_type.startswith('thumb'): self.thumb()
            elif self.media_type.startswith('playlist'): self.playlist()
            elif self.media_type.startswith('playlist'): self.playlist()
            elif self.media_type.startswith('audio'): self.audio()
            elif self.media_type.startswith('video'): self.video()
            elif self.media_type.startswith('hls'): self.hls()
            elif self.media_type.startswith('low'): self.low()
            elif self.media_type.startswith('sub'): self.sub()
            elif self.media_type.startswith('sprite'): self.sprite()
        return check_media(url=self.url, media_type=self.media_type)


    def _load_variables(self):
        self.output_path = os.path.join(self.data_dir, f'{self.media_type}.%(ext)s')
        print(f'Downloading {self.media_type} for {self.url}')
        self.ydl_opts = {"outtmpl": self.output_path}
        self.ydl_opts.update(ydl_global_opts)
        if cookies := check_media(self.url, 'cookies') or get_global_cookies_file(): self.ydl_opts["cookiefile"] = cookies
        self.meta = get_meta(self.url)
        if int(self.meta.get('duration') or 0) > max_video_duration: raise ValueError("Video too long for this app to handle")
        self.timestamps = re.search(r'_(\d+\.?\d*)-(\d+\.?\d*)', self.media_type)
        self.start_time = None
        self.end_time = None
        self.res = int((re.search(r'(\d+)', self.media_type) and re.search(r'(\d+)', self.media_type).group(1) or str(default_quality)))
        
        if self.timestamps:
            try:
                self.start_time = float(self.timestamps.group(1))
                self.end_time = float(self.timestamps.group(2))
                self.ydl_opts.update({'download_ranges': yt_dlp.utils.download_range_func(None, [(self.start_time, self.end_time)]), 'force_keyframes_at_cuts': True})
                print(f"Downloading section {self.start_time}-{self.end_time}")
            except ValueError:
                print("Error parsing start/end times from media_type")


    def thumb(self):
        thumb_url = self.meta['thumbnail']
        video_width = self.meta.get('width')
        video_height = self.meta.get('height')
        try:
            download_media_file(thumb_url, os.path.join(self.data_dir, 'thumb-orig'))
        except Exception as e:
            pprint_exc(e)
        try:
            if video_width and video_height:
                thumb_file = check_media(url=self.url, media_type='thumb-orig')
                if not thumb_file:
                    print('Direct thumbnail download did not succeed. Downloading using yt-dlp.')
                    self.ydl_opts.update({'writethumbnail': True, 'skip_download': True})
                    YTDLP.download(self.url, self.ydl_opts)
                    thumb_file = check_media(url=self.url, media_type='thumb-orig')

                ffmpeg_command = [
                    '-y',
                    '-i', thumb_file,
                    '-vf', f'crop=w=min(iw\\,ih*({video_width}/{video_height})):h=min(ih\\,iw*({video_height}/{video_width})):x=(iw-ow)/2:y=(ih-oh)/2',
                    os.path.join(self.data_dir, 'thumb.jpg')
                ]
                if not FFMPEG(self.url, ffmpeg_command).success: raise RuntimeError('FFMPEG failed to crop thumbnail')
                print(f"Thumbnail cropped to video aspect ratio {video_width}:{video_height} using ffmpeg")
                os.remove(thumb_file)
            else:
                print("Video dimensions not found in meta, skipping thumbnail cropping.")
        except Exception as e:
            print(f"Error cropping thumbnail: {e}")


    def playlist(self):
        query = parse_qs(urlparse(self.url).query).get('q')
        entries = []
        if query:
            input_entries = search(query[0], 'ytsearch10')
        else:
            self.ydl_opts.update({"playlistend": 10, 'quiet': True, 'skip_download': True})
            del self.ydl_opts['noplaylist']
            print(f'Running YT-DLP with opts: {self.ydl_opts}')
            input_entries = YTDLP.get_info(self.url, self.ydl_opts).get('entries') or {}

        for entry in input_entries:
            entry['original_url'] = normalize_url(entry['original_url'])
            entries.append(clean_meta(entry))
        for entry in input_entries:
            preload(meta=entry, playlist=entries)

        with open(os.path.join(get_data_dir(self.url), 'playlist.json'), 'w') as f:
            json.dump(entries, f)


    def audio(self):
        if self.meta.get('is_live'): raise NotImplementedError('Livestream transcoding is not supported')
        self.ydl_opts.update({"format": "bestaudio/best", "extract_audio": True, "outtmpl": os.path.join(self.data_dir, f'{self.media_type}.mp3')})
        YTDLP.download(self.url, self.ydl_opts)


    def video(self):
        if self.meta.get('is_live'): raise NotImplementedError('Livestream transcoding is not supported')
        if cookies := check_media(self.url, 'cookies') or get_global_cookies_file():
            mark_watched = lambda: YTDLP.get_info(self.url, ydl_global_opts | {'mark_watched': True, 'cookiefile': cookies})
            Thread(target=mark_watched).start()
        height_param = "" if self.media_type.startswith('video-best') else f'[height<={self.res}]'
        if self.timestamps:
            if vid := check_res_at_least(self.url, self.res):
                FFMPEG(self.url, ['-i', vid, "-ss", f'{self.start_time}', "-to", f'{self.end_time}', '-vf', f'scale=-2:{self.res}', os.path.join(get_data_dir(self.url), self.media_type + '.mp4')])
            else:
                self.ydl_opts.update({"format": f"bestvideo{height_param}+bestaudio/best", "outtmpl": os.path.join(self.data_dir, f'{self.media_type}.%(ext)s')})
                YTDLP.download(self.url, self.ydl_opts)
        else:
            if vid := check_res_at_least(self.url, self.res):
                FFMPEG(self.url, ['-i', vid, '-vf', f'scale=-2:{self.res}', os.path.join(get_data_dir(self.url), self.media_type + '.mp4')])
            else:
                success = False
                temp_video = None
                try:
                    self.ydl_opts.update({"format": f"bestvideo{height_param}/best", "outtmpl": os.path.join(self.data_dir, f'temp-{self.media_type}.%(ext)s')})
                    YTDLP.download(self.url, self.ydl_opts)
                    audio_file = check_media(self.url, 'audio') or MediaDownloader(self.url, 'audio').run()
                    temp_video = check_media(self.url, f'temp-{self.media_type}')
                    success = FFMPEG(self.url, ['-i', audio_file, '-i', temp_video, "-c:a", "copy", "-c:v", "copy", temp_video.replace('temp-', '')]).success
                except Exception as e:
                    pprint_exc(e)
                finally:
                    if temp_video: os.remove(temp_video)
                if not success:
                    print(f'Falling back to standard video download due to FFMPEG error')
                    self.ydl_opts.update({"format": f"bestvideo{height_param}+bestaudio/best", "outtmpl": os.path.join(self.data_dir, f'{self.media_type}.%(ext)s')})
                    YTDLP.download(self.url, self.ydl_opts)


    def hls(self):
        if self.meta.get('is_live'): raise NotImplementedError('Livestream transcoding is not supported')
        res_str = 'audio' if 'audio' in self.media_type else str(self.res)
        hls_url_dir = os.path.join(gen_pathname(self.url), f"hls_playlist-{res_str}")
        hls_output_dir = os.path.join(download_path, hls_url_dir)
        hls_segment_duration = hls_audio_duration if res_str == 'audio' else hls_duration
        os.makedirs(hls_output_dir, exist_ok=True)

        temp_m3u8_path = os.path.join(self.data_dir, f'{self.media_type}.m3u8.temp')
        m3u8_path = os.path.join(self.data_dir, f'{self.media_type}.m3u8')

        sources = get_video_sources(self.url)
        video_url = None
        audio_source = None
        video_file_path = check_media(self.url, 'audio') if res_str == 'audio' else check_res_at_least(self.url, self.res)

        if not video_file_path:
            audio_source = check_media(self.url, 'audio')
            if res_str in sources:
                if res_str == 'audio':
                    audio_source = audio_source or sources[res_str]
                else:
                    video_url = sources[res_str]
                    audio_source = audio_source or sources.get('audio_drc') or sources.get('audio') or sources.get('audio_presumed')

            if not video_url and not audio_source:
                print('Could not find any suitable streamable video format: Downloading the whole video')
                video_file_path = MediaDownloader(self.url, 'audio' if 'audio' in self.media_type else f'video-{self.res}').run()

        ffmpeg_command = [
            '-c:v', 'libx264',
            '-crf', '22',
            '-r', f'{self.meta.get("fps") or "30"}',
            '-c:a', 'aac',
            '-ar', '44100',
            '-f', 'hls',
            '-vf', f'scale=-2:{self.res}',
            '-force_key_frames', f'expr:gte(t,n_forced*{hls_segment_duration})',
            '-hls_time', f'{hls_segment_duration}',
            '-hls_playlist_type', 'vod',
            '-hls_segment_filename', os.path.join(hls_output_dir, 'segment%04d.ts'),
            temp_m3u8_path
        ]

        if video_url:
            ffmpeg_command = ['-i', video_url] + ffmpeg_command
        if audio_source:
            ffmpeg_command = ['-i', audio_source] + ffmpeg_command
        if video_file_path:
            ffmpeg_command = ['-i', video_file_path] + ffmpeg_command

        seg_time = 0
        seg_num = 0
        duration = self.meta["duration"]
        hls_url_dir = os.path.join(gen_pathname(self.url), f"hls_playlist-{res_str}")
        seg_path = f"/hls_stream?url={quote_plus(self.url)}&quality={res_str}&seg="

        with open(m3u8_path, "w") as f:
            f.write(f"#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:{hls_segment_duration}\n#EXT-X-MEDIA-SEQUENCE:0\n#EXT-X-PLAYLIST-TYPE:VOD\n")
            while seg_time < duration:
                time_to_add = min(hls_segment_duration, self.meta["duration"] - seg_time)
                f.write(f"#EXTINF:{time_to_add:.6f},\n{seg_path}{seg_num}\n")
                seg_time += time_to_add
                seg_num += 1
            f.write("#EXT-X-ENDLIST\n")

        def download_hls_files():
            nonlocal video_file_path
            try:
                if not video_file_path:
                    ff = FFMPEG(self.url)
                    Thread(target=ff.run, args=[ffmpeg_command]).start()
                    time.sleep(2)
                    video_file_path = MediaDownloader(self.url, 'audio' if 'audio' in self.media_type else f'video-{self.res}').run()
                    if not video_file_path: raise RuntimeError('Could not download video')
                    print(f'Killing FFMPEG {ff.ff_id} due to local media availability')
                    ff.kill()
                    os.rename(m3u8_path, temp_m3u8_path)
                    MediaDownloader(self.url, self.media_type).run()
                elif FFMPEG(self.url, ffmpeg_command).success:
                    print(f"FFMPEG Finished HLS Conversion!")
                    os.remove(temp_m3u8_path)
                else:
                    print(f"An FFMPEG error occurred during HLS conversion")
            except Exception as e:
                print(f"An unexpected error occurred during HLS conversion")
                pprint_exc(e)

        Thread(target=download_hls_files, daemon=True).start()


    def low(self):
        if self.meta.get('is_live'): raise NotImplementedError('Livestream transcoding is not supported')
        ffmpeg_command = [
            '-i', MediaDownloader(self.url, 'video').run(),
            '-c:v', 'libx265',
            '-crf', '34',
            '-c:a', 'aac',
            '-r', '30',
            '-vf', 'scale=-2:240',
            '-preset', 'veryfast',
            os.path.join(get_data_dir(get_url(request)), 'low.mp4')
        ]
        FFMPEG(self.url, ffmpeg_command)


    def sub(self):
        lang = self.media_type.split('-')[1]
        print(f'downloading sub for {lang=}')

        try:
            sub = {**(self.meta.get('subtitles') or {}), **(self.meta.get('automatic_captions') or {})}.get(lang) or ''
            for i in sub:
                if i.get('ext') == 'srt':
                    sub_url = i.get('url')
                    if sub_url:
                        download_media_file(sub_url, os.path.join(self.data_dir, self.media_type), 'srt')
                        break
                if i.get('ext') == 'vtt':
                    sub_url = i.get('url')
                    if sub_url:
                        download_media_file(sub_url, os.path.join(self.data_dir, self.media_type), 'vtt')
                        break
            else:
                raise FileNotFoundError('Selected subtitles not found')
            file = check_media(url=self.url, media_type=self.media_type)
            if not file:
                raise FileNotFoundError('Selected subtitles not found')
            with open(file, 'r') as f:
                if '-->' not in f.read():
                    raise TypeError('Downloaded subtitles are not valid')

        except Exception as e:
            print(f'Direct subtitle download did not succeed: {e}. Downloading using yt-dlp.')
            if f := check_media(url=self.url, media_type=self.media_type):
                os.remove(f)
            self.ydl_opts.update({'writesubtitles': True, 'skip_download': True, 'subtitleslangs': [lang]})
            YTDLP.download(self.url, self.ydl_opts)

        file = check_media(url=self.url, media_type=self.media_type)
        if file and file.endswith('srt'):
            with open(file, 'r') as f:
                data = f.read()
            data = re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})', r'\1.\2', data)
            with open(file, 'w') as f:
                f.write('WEBVTT\n' + data)


    def sprite(self):
        if self.meta.get('is_live'): raise NotImplementedError('Livestream transcoding is not supported')
        if self.meta["duration"] > generate_sprite_below: raise ValueError(f"Video too long to generate sprite! ({self.meta["duration"]}s)")
        if not self.meta.get('height') and not self.meta.get('width'): raise TypeError('Sprite not available on non-video media!')
        video_path = check_media(url=self.url, media_type='video')
        sprite_dir = os.path.join(self.data_dir, 'temp_sprite')
        os.makedirs(sprite_dir, exist_ok=True)
        if not video_path:
            MediaDownloader(self.url, 'video').run()
            video_path = check_media(url=self.url, media_type='video')
        if video_path:
            frame_interval = 10 # seconds
            frame_width = 160
            frame_height = 90
            frames_per_row = 10

            ffmpeg_command = [
                '-i', video_path,
                '-vf', f'fps={1/frame_interval},scale={frame_width}:{frame_height}',
                os.path.join(sprite_dir, 'frame_%04d.jpg')
            ]

            try:
                if not FFMPEG(self.url, ffmpeg_command).success: raise RuntimeError('FFMPEG failed to extract sprite')
                frame_files = sorted(os.listdir(sprite_dir))
                num_frames = len(frame_files)
                num_rows = math.ceil(num_frames / frames_per_row)
                canvas_width = frames_per_row * frame_width
                canvas_height = num_rows * frame_height
                print(f'Sprite: generated {num_frames} frames. Combining into a {canvas_width}x{canvas_height} sprite.')

                sprite_image = Image.new('RGB', (canvas_width, canvas_height))

                for i, frame_file in enumerate(frame_files):
                    frame_path = os.path.join(sprite_dir, frame_file)
                    with Image.open(frame_path) as img:
                        row = i // frames_per_row
                        col = i % frames_per_row
                        x = col * frame_width
                        y = row * frame_height
                        sprite_image.paste(img, (x, y))
                sprite_image.save(os.path.join(self.data_dir, 'sprite.jpg'))
                shutil.rmtree(sprite_dir)
            except Exception as e:
                print(f"Sprite error: {e}")



def host_file(url: str, media_type='video', download_name: str | None = None):
    if not url: return jsonify({"error": "URL parameter is required"}), 400
    file = MediaDownloader(url, media_type).run()
    if file:
        if download_name:
            if '-' in media_type: download_name += '-' + media_type.split('-', 1)[-1]
            download_name += os.path.splitext(file)[1]
        return send_file_partial(file, download_name=download_name)
    return jsonify({"error": f"Cannot gather {media_type}"}), 404



@app.route('/')
def index():
    print('Started serving root')
    ydl_version = External.get_ytdlp_version()
    ffmpeg_version = External.get_ffmpeg_version(ffmpeg)
    print('Stopped serving root')
    return render_template('index.html', ydl_version=ydl_version, app_version=app_version, ffmpeg_version=ffmpeg_version, app_title=app_title, theme_color=theme_color, amoled_bg=amoled_bg)


@app.route('/watch')
def watch():
    print('Started serving watch')
    ydl_version = External.get_ytdlp_version()
    ffmpeg_version = External.get_ffmpeg_version(ffmpeg)
    url = get_url(request)
    
    video_width = 1280
    video_height = 720
    video_title = app_title

    if check_media(url, 'meta'):
        meta = get_meta(url)
        video_width = meta.get('width') or video_width
        video_height = meta.get('height') or video_height
        video_title = meta.get('title') or app_title
    preload(url)

    print('Stopped serving watch')
    return render_template('watch.html', original_url=url, ydl_version=ydl_version, app_version=app_version, ffmpeg_version=ffmpeg_version, app_title=app_title, theme_color=theme_color, amoled_bg=amoled_bg, video_width=video_width, video_height=video_height, video_title=video_title)


@app.route('/iframe')
def iframe():
    print('Started serving iframe')
    url = get_url(request)
    
    video_width = 1280
    video_height = 720

    if check_media(url, 'meta'):
        meta = get_meta(url)
        video_width = meta.get('width', video_width)
        video_height = meta.get('height', video_height)
    preload(url)

    print('Stopped serving iframe')
    return render_template('iframe.html', app_title=app_title, theme_color=theme_color, video_width=video_width, video_height=video_height)


@app.route('/thumb')
def serve_thumbnail():
    try:
        url = get_url(request)
        return host_file(url, 'thumb')
    except Exception as e:
        return pprint_exc(e)


@app.route('/sprite')
def serve_sprite():
    url = get_url(request)
    return host_file(url, 'sprite')


@app.route('/sb')
def get_sponsor_segments():
    return get_sb(get_url(request)) or []


@app.route('/raw')
def raw():
    html_template = f'<video controls autoplay><source src="/download?url={get_url(request)}" type="video/mp4"></video>'
    return html_template


@app.route('/download')
def download_media():
    try:
        res = (request.args.get('quality') or '')
        start_time = request.args.get('start', 0, type=float)
        end_time = request.args.get('end', 0, type=float)
        
        media_type = 'audio' if res == 'audio' else f'video-{res}'.removesuffix('-')
        
        if start_time > 0 or end_time > 0:
            media_type += f'_{start_time:.1f}-{end_time:.1f}'

        url = get_url(request)
        video_title = get_meta(url).get('title')
        return host_file(url, media_type, download_name=video_title)

    except Exception as e:
        return pprint_exc(e)


@app.route('/low')
def download_low_quality():
    try:
        return host_file(get_url(request), 'low')
    except Exception as e:
        return pprint_exc(e)


@app.route('/direct')
def resp_direct_stream():
    try:
        url = get_url(request)

        if check_media(url, 'video'):
            return host_file(url, 'video')
        if check_media(url, 'direct'):
            return host_file(url, 'direct')
        if direct_quality := get_direct_quality(url):
            if direct_quality is True:
                return host_file(url, 'direct')
            return stream_media_file(direct_quality)

        res = get_good_quality(get_video_formats(url)) 
        media_type = f'hls-{res}'.removesuffix('-')
        return host_file(get_url(request), media_type)
    except Exception as e:
        return pprint_exc(e)


@app.route('/subtitle')
def serve_subtitle():
    return host_file(get_url(request), f'sub-{request.args.get("lang")}')


@app.route('/meta')
def serve_meta():
    try:
        url = get_url(request)
        if not url: return jsonify({"error": "URL parameter is required"}), 400
        return clean_meta(get_meta(url))
    except Exception as e:
        return pprint_exc(e)


@app.route('/manifest.json')
def serve_manifest():
    return render_template('manifest.json', app_title=app_title, theme_color=theme_color, amoled_bg=amoled_bg)


@app.route('/playlist')
def serve_playlist():
    try:
        return host_file(get_url(request), 'playlist')
    except Exception as e:
        return pprint_exc(e)


@app.route('/favicon.svg')
def serve_favicon():
    with open('static/favicon.svg', 'r') as f:
        favicon = f.read()
    favicon = favicon.replace('#ff7300', theme_color)
    return Response(favicon, mimetype='image/svg+xml')


@app.route('/sw.js')
def serve_sw():
    with open('static/sw.js', 'r') as f:
        sw = f.read()
    return Response(sw, mimetype='text/javascript')


@app.route('/hls')
def download_hls():
    try:
        res = (request.args.get('quality') or '')  
        media_type = f'hls-{res}'.removesuffix('-')
        return host_file(get_url(request), media_type)
    except Exception as e:
        return pprint_exc(e)


@app.route('/hls_stream')
def hls_stream():
    url = get_url(request)
    data_dir = get_data_dir(url)
    quality = request.args.get('quality')
    seg = request.args.get('seg')
    file = os.path.join(data_dir, f'hls_playlist-{quality}/segment{seg:>0{4}}.ts')

    if not os.path.exists(file):
        media_type = f'hls-{quality}'.removesuffix('-')
        host_file(get_url(request), media_type)
        return jsonify({"error": "File not found"}), 404

    return send_file_partial(file)


@app.route('/search')
def serve_search():
    try:
        if demo := (os.environ.get('DEMO_VIDEO')): return demo
        query = request.args.get('q')
        meta = search(query)[0]
        url = meta.get('original_url') or ''
        final_url = append_query_to_url(url, query)

        preload(final_url, meta)
        return final_url
    except Exception as e:
        return pprint_exc(e)


@app.route('/cookies', methods=['POST'])
def cookies_endpoint():
    try:
        url = get_url(request)
        cookies = request.form.get('cookies')
        if not cookies: return jsonify({"error": "cookies are required"}), 400
        if file := get_global_cookies_file():
            with open(file, 'r') as f:
                cookies += '\n' + f.read()
        os.makedirs(get_data_dir(url), exist_ok=True)
        with open(os.path.join(get_data_dir(url), 'cookies.txt'), 'w') as f:
            f.write(cookies)
        return "OK", 200

    except Exception as e:
        return pprint_exc(e)


@app.route('/cancel')
def cancel_download():
    url = get_url(request)
    if not url: return jsonify({"error": "URL parameter is required"}), 400
    cancelled_count = Processes.rm_all(url)
    return jsonify({"message": f"Cancelled {cancelled_count} ongoing processes"}), 200


@app.after_request
def after_request(response):
    response.headers.add('Accept-Ranges', 'bytes')
    response.headers.add('Content-Security-Policy', "frame-src *")
    return response
