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



Downloader.get_app_version()
app_version = Downloader.get_app_version()



class YTDLP:
    @staticmethod
    def download(url, opts):
        print(f'Running YT-DLP download with opts: {opts}')
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    ydl.download_with_info_file(check_media(url, 'meta'))
                except Exception as e:
                    pprint_exc(e)
                    print('An error occured when downloading with meta. Downloading without meta...')
                    ydl.download(unquote(url))
        except Exception as e:
            if (cookies := get_global_cookies_file(True)):
                pprint_exc(e)
                print('An error occured when downloading. Downloading with cookies...')
                opts["cookiefile"] = cookies
                print(f'Running YT-DLP download with opts: {opts}')
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download(unquote(url))
            else:
                print('An error occured when downloading. Providing cookies may help with this issue.')
                raise e


    @staticmethod
    def get_info(url, opts):
        print(f'Running YT-DLP extract_info with opts: {opts}')
        try:
            with yt_dlp.YoutubeDL(json.loads(json.dumps(opts))) as ydl:
                return ydl.sanitize_info(ydl.extract_info(url, download=False))
        except Exception as e:
            if (cookies := get_global_cookies_file(True)):
                pprint_exc(e)
                print('An error occured when downloading. Downloading with cookies...')
                opts["cookiefile"] = cookies
                print(f'Running YT-DLP extract_info with opts: {opts}')
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.sanitize_info(ydl.extract_info(url, download=False))
            else:
                print('An error occured when downloading. Providing cookies may help with this issue.')
                raise e


class FFMPEG:
    def __init__(self, ffmpeg_command=None):
        """
        Provide ffmpeg_command to run synchronously. Check with `success`
        """
        self._p = None
        self.ffmpeg = ffmpeg
        self.ff_id = sha1(f'{time.time()}'.encode()).hexdigest()[:6]
        self.success = False
        self.start_time = time.time()
        if ffmpeg_command and self.ffmpeg:
            self.run(ffmpeg_command)

    def kill(self):
        if self._p is None: return
        self._p.kill()
        time.sleep(0.2)
        print(f'[FFMPEG {self.ff_id}] Killed')

    def run(self, ffmpeg_command):
        """
        Also runs synchronously, but can be placed in `Thread`
        """
        if not self.ffmpeg: return None
        ffmpeg_command = [self.ffmpeg] + ffmpeg_command
        
        print(f'[FFMPEG {self.ff_id}] Executing {ffmpeg_command}')
        self._p = subprocess.Popen(ffmpeg_command, stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
        for line in self._p.stdout:
            print(f'[FFMPEG {self.ff_id}] {line.decode().strip()}')
            if time.time() - self.start_time > 3600:
                self.kill()
                self.success = False
                raise TimeoutError()
        self._p.wait()
        print(f'[FFMPEG {self.ff_id}] Finished')
        self.success = True



def pprint_exc(e, code = 500):
    error = (re.sub(r'[^\x20-\x7e]',r'', re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", str(e))))
    print(error)
    return error, code


def gen_pathname(url: str):
    return sha1(url.encode()).hexdigest()


def get_data_dir(url):
    data_dir = os.path.join(download_path, gen_pathname(url))
    return data_dir


def get_global_cookies_file(force = False):
    if cookies_only_on_failure and not force: return None
    if os.path.exists('cookies.txt'): return 'cookies.txt'
    return None


def get_meta(url: str):
    with FileCachingLock(url, 'meta') as cache:
        print(cache)
        if cache:
            try:
                with open(cache, 'r') as f: return json.load(f)
            except:
                print('Meta file invalid - Regenerating...')
        print(f'downloading meta for {url}')
        ydl_opts = {'quiet': True, 'skip_download': True}
        ydl_opts.update(ydl_global_opts)
        if cookies := check_media(url, 'cookies') or get_global_cookies_file(): ydl_opts["cookiefile"] = cookies
        info = YTDLP.get_info(url, ydl_opts)
        info['original_url'] = url
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



def get_video_formats(url = None, meta = None, protocol = None):
    resolutions = []
    if not meta:
        meta = get_meta(url)
    formats = meta.get('formats', [])
    for f in formats:
        if f.get('vcodec') != 'none' and f.get('height') and f.get('height') not in resolutions:
            if protocol and protocol != f.get('protocol'): continue
            resolutions.append(f['height'])
    return resolutions



def get_video_sources(url, protocol = None):
    sources = {}
    best_audio = 0
    meta = get_meta(url)
    formats = meta.get('formats') or []
    for f in formats:
        video_name = f"{(f.get('height') or '')}" if (f.get('vcodec') or 'none').lower() != 'none' else ''
        audio_name = ''
        if f.get('acodec', 'none') != 'none':
            audio_name = 'audio_drc' if 'drc' in f"{f.get('format_id')} {f.get('format_note')}".lower() else 'audio'
        if 'audio' in (f.get('format_id') or '') or (f.get('acodec') or 'audio_presumed') == 'audio_presumed':
            audio_name = 'audio_presumed'
        name = video_name + audio_name
        quality = float(f.get('quality') or 0)
        if not name: continue
        if protocol and protocol != f.get('protocol'): continue

        if name.startswith('audio') and quality < best_audio:
            best_audio = quality
            sources[name] = f['url']
        elif name not in sources:
            sources[name] = f['url']
    return sources


def check_res_at_least(url:str, res: int):
    for f in sorted(get_video_formats(url)):
        if type(f) == int and f >= res:
            if file := check_media(url, f'video-{f}'):
                return file


def get_subtitles(meta: dict):
    subs = {**(meta.get('subtitles') or {}), **(meta.get('automatic_captions') or {})}
    all_subtitles = []
    for lang, subs in subs.items():
        if subs:
            all_subtitles.append(lang)
    return all_subtitles


def get_direct_quality(url):
    sources = get_video_sources(url, protocol='https')
    for s in sources:
        if 'audio' in s and not s.startswith('audio'):
            return sources[s]
    sources = get_video_sources(url, protocol='m3u8_native')
    q = get_good_quality(get_video_formats(url, protocol='m3u8_native'))
    vid_src = None
    audio_src = None
    for s in sources.keys():
        if not audio_src and 'audio' in s: audio_src = s
        if not vid_src and str(q) in s:
            vid_src = s
            if 'audio' in s: audio_src = s
    if vid_src and audio_src:
        if audio_src == vid_src: audio_src = None
        hls_data = [
            '#EXTM3U',
            '#EXT-X-VERSION:3',
            f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio_grp",NAME="English",DEFAULT=YES,AUTOSELECT=YES,URI="{sources[audio_src]}"' if audio_src else "",
            f'#EXT-X-STREAM-INF:BANDWIDTH=1500000{",AUDIO=\"audio_grp\"" if audio_src else ""}',
            f'{sources[vid_src]}'
        ]
        with open(os.path.join(get_data_dir(url), 'direct.m3u8'), 'w') as f:
            f.write('\n'.join(hls_data))
        return True
    return None


def get_good_quality(formats: list):
    if not isinstance(formats, list) or not formats: return default_quality
    sorted_formats = sorted(formats)
    for quality in sorted_formats:
        if quality >= default_quality:
            print(f'Choosing quality {quality} for current video')
            return quality
    print(f'Choosing quality {sorted_formats[-1]} for current video')
    return sorted_formats[-1]


def search(query, search_engine='auto'):
    print(f'Searching for {query}')
    ydl_opts = {'quiet': True, 'skip_download': True, 'default_search': search_engine}
    ydl_opts.update(ydl_global_opts)
    info = YTDLP.get_info(query, ydl_opts)
    entries = info.get('entries') or [{}]
    for entry in entries:
        entry['original_url'] = normalize_url(append_query_to_url(entry['original_url'], query))
    return entries


def generate_chapters(desc: str):
    try:
        chapters = []
        last_time = 0
        def time_to_int(t: str):
            parts = t.split(':')
            secs = int(parts[-1])
            if len(parts) >= 2: secs += int(parts[-2]) * 60
            if len(parts) >= 3: secs += int(parts[-3]) * 3600
            return secs

        for line in desc.splitlines():
            if line and line[0].isdigit():
                line = line.strip()
                lastchar = 0
                for i in line:
                    if i.isdigit() or i == ':':
                        lastchar += 1
                if lastchar < 3 or ':' not in line[0:lastchar]: continue
                time = time_to_int(line[0:lastchar])
                if time < last_time: break
                last_time = time
                chapters.append({'time': time, 'label': line[lastchar:].strip()})
        return chapters if len(chapters) > 1 else []
    except Exception:
        return []


def clean_meta(raw_meta: dict):
    meta = {}
    meta['title'] = raw_meta.get('title') or ''
    meta['uploader'] = raw_meta.get('uploader') or ''
    try:
        meta['formats'] = get_video_formats(meta=raw_meta)
    except BaseException as e:
        meta['formats'] = jsonify({'error': (re.sub(r'[^\x20-\x7e]',r'', re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", str(e))))}), 403
    meta['duration'] = f'{raw_meta.get("duration") or 0}'
    meta['subtitles'] = get_subtitles(raw_meta)
    meta['width'] = raw_meta.get('width')
    meta['height'] = raw_meta.get('height')
    meta['url'] = raw_meta.get('original_url')
    meta['default_quality'] = 'audio' if 'Music' in (raw_meta.get('categories') or []) and audio_visualizer else get_good_quality(meta['formats'])
    meta['load_default_quality'] = load_default_quality
    meta['playlist_support'] = playlist_support
    meta['auto_bg_playback'] = auto_bg_playback
    meta['audio_visualizer'] = audio_visualizer
    meta['chapters'] = generate_chapters(raw_meta.get('description'))
    if raw_meta.get('is_live'):
        meta['formats'] = []
        meta['load_default_quality'] = False
        meta['subtitles'] = []
        meta['duration'] = '0'
    return meta


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


def keepalive(data_dir):
    with open(os.path.join(data_dir, 'keepalive'), 'w') as f:
        f.write(str(int(time.time())))


def normalize_url(url):
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)

    new_query = urlencode(query_params, doseq=True)
    url = urlunparse(parsed_url._replace(query=new_query))

    if '.' not in url:
        url = 'https://youtube.com/watch?v=' + url
    if '/watch?v=' in url:
        yt_url = 'https://youtube.com/watch?v=' + url.split('/watch?v=')[1]
        try:
            if get_meta(yt_url):
                url = yt_url
        except: pass
    return url


def get_url(req):
    url = req.args.get('v') or req.args.get('url') or None
    if url is None or len(url) < 3: return None
    return normalize_url(url)


def append_query_to_url(url, query):
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    query_params['q'] = query
    new_query_string = urlencode(query_params, doseq=True)
    return urlunparse(parsed_url._replace(query=new_query_string))


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



def check_media(url: str, media_type: str):
    print(f'Checking media for {url=} and {media_type=}')
    data_dir = get_data_dir(url)
    try:
        for i in os.listdir(data_dir):
            if i.endswith('.part'): continue
            if i.endswith('.ytdl'): continue
            if i.endswith('.temp'): continue
            if i.count('_') != media_type.count('_'): continue
            if i.startswith(media_type):
                path = os.path.join(data_dir, i)
                print(f'Serving {path}')
                keepalive(data_dir)
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
            print(f'Waiting for download of {self.media_type} for {self.data_dir.split("/")[-1]}')
        
        if cached_media := check_media(url=self.url, media_type=self.media_type):
            print(f'Cache hit for {self.media_type}!')
            self.url = None
            return cached_media
        
        os.makedirs(self.data_dir, exist_ok=True)
        keepalive(self.data_dir)
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
        if cookies := check_media(url, 'cookies') or get_global_cookies_file(): ydl_opts["cookiefile"] = cookies
        meta = get_meta(url)
        if int(meta.get('duration') or 0) > max_video_duration: raise ValueError("Video too long for this app to handle")
        timestamps = re.search(r'_(\d+\.?\d*)-(\d+\.?\d*)', media_type)
        start_time = None
        end_time = None
        res = int((re.search(r'(\d+)p', media_type) and re.search(r'(\d+)p', media_type).group(1) or str(default_quality)).removesuffix('p'))
        
        if timestamps:
            try:
                start_time = float(timestamps.group(1))
                end_time = float(timestamps.group(2))
                ydl_opts.update({'download_ranges': yt_dlp.utils.download_range_func(None, [(start_time, end_time)]), 'force_keyframes_at_cuts': True})
                print(f"Downloading section {start_time}-{end_time}")
            except ValueError:
                print("Error parsing start/end times from media_type")


        if media_type == 'thumb':
            thumb_url = meta['thumbnail']
            video_width = meta.get('width')
            video_height = meta.get('height')
            try:
                download_media_file(thumb_url, os.path.join(data_dir, 'thumb_orig'))
            except Exception:
                pass
            try:
                if video_width and video_height:
                    thumb_file = check_media(url=url, media_type='thumb_orig')
                    if not thumb_file:
                        print('Direct thumbnail download did not succeed. Downloading using yt-dlp.')
                        ydl_opts.update({'writethumbnail': True, 'skip_download': True})
                        YTDLP.download(url, ydl_opts)
                        thumb_file = check_media(url=url, media_type='thumb_orig')

                    ffmpeg_command = [
                        '-y',
                        '-i', thumb_file,
                        '-vf', f'crop=w=min(iw\\,ih*({video_width}/{video_height})):h=min(ih\\,iw*({video_height}/{video_width})):x=(iw-ow)/2:y=(ih-oh)/2',
                        os.path.join(data_dir, 'thumb.jpg')
                    ]
                    if not FFMPEG(ffmpeg_command).success: raise RuntimeError('FFMPEG failed to crop thumbnail')
                    print(f"Thumbnail cropped to video aspect ratio {video_width}:{video_height} using ffmpeg")
                    os.remove(thumb_file)
                else:
                    print("Video dimensions not found in meta, skipping thumbnail cropping.")
                    shutil.move(thumb_file, thumb_file.replace('thumb_orig', 'thumb'))
            except Exception as e:
                print(f"Error cropping thumbnail: {e}")


        elif media_type.startswith('playlist'):
            query = parse_qs(urlparse(url).query).get('q')
            entries = []
            if query:
                input_entries = search(query[0], 'ytsearch10')
            else:
                ydl_opts.update({"playlistend": 10, 'quiet': True, 'skip_download': True})
                del ydl_opts['noplaylist']
                print(f'Running YT-DLP with opts: {ydl_opts}')
                input_entries = YTDLP.get_info(url, ydl_opts).get('entries') or {}

            for entry in input_entries:
                entry['original_url'] = normalize_url(entry['original_url'])
                entries.append(clean_meta(entry))
            for entry in input_entries:
                preload(meta=entry, playlist=entries)

            with open(os.path.join(get_data_dir(url), 'playlist.json'), 'w') as f:
                json.dump(entries, f)


        elif media_type.startswith('audio'):
            if meta.get('is_live'): raise NotImplementedError('Livestream transcoding is not supported')
            ydl_opts.update({"format": "bestaudio/best", "extract_audio": True, "outtmpl": os.path.join(data_dir, f'{media_type}.mp3')})
            YTDLP.download(url, ydl_opts)


        elif media_type.startswith('video'):
            if meta.get('is_live'): raise NotImplementedError('Livestream transcoding is not supported')
            if cookies := check_media(url, 'cookies') or get_global_cookies_file(): ydl_opts["mark_watched"] = True
            height_param = "" if media_type.startswith('video-best') else f'[height<={res}]'
            if timestamps:
                if vid := check_res_at_least(url, res):
                    FFMPEG(['-i', vid, "-ss", f'{start_time}', "-to", f'{end_time}', '-vf', f'scale=-2:{res}', os.path.join(get_data_dir(url), media_type + '.mp4')])
                else:
                    ydl_opts.update({"format": f"bestvideo{height_param}+bestaudio/best", "outtmpl": os.path.join(data_dir, f'{media_type}.%(ext)s')})
                    YTDLP.download(url, ydl_opts)
            else:
                if vid := check_res_at_least(url, res):
                    FFMPEG(['-i', vid, '-vf', f'scale=-2:{res}', os.path.join(get_data_dir(url), media_type + '.mp4')])
                else:
                    try:
                        ydl_opts.update({"format": f"bestvideo{height_param}/best", "outtmpl": os.path.join(data_dir, f'temp-{media_type}.%(ext)s')})
                        YTDLP.download(url, ydl_opts)
                        audio_file = check_media(url, 'audio') or download_file(url, 'audio')
                        temp_video = check_media(url, f'temp-{media_type}')
                        success = FFMPEG(['-i', audio_file, '-i', temp_video, "-c:a", "copy", "-c:v", "copy", temp_video.replace('temp-', '')]).success
                    finally:
                        if temp_video: os.remove(temp_video)
                    if not success:
                        print(f'Falling back to standard video download due to FFMPEG error')
                        ydl_opts.update({"format": f"bestvideo{height_param}+bestaudio/best", "outtmpl": os.path.join(data_dir, f'{media_type}.%(ext)s')})
                        YTDLP.download(url, ydl_opts)


        elif media_type.startswith('hls'):
            if meta.get('is_live'): raise NotImplementedError('Livestream transcoding is not supported')
            hls_url_dir = os.path.join(gen_pathname(url), f"hls_playlist-{res}")
            hls_output_dir = os.path.join(download_path, hls_url_dir)
            os.makedirs(hls_output_dir, exist_ok=True)

            temp_m3u8_path = os.path.join(data_dir, f'{media_type}.m3u8.temp')
            m3u8_path = os.path.join(data_dir, f'{media_type}.m3u8')
            hls_duration = 10
            res_str = str(res)

            sources = get_video_sources(url)
            video_url = None
            audio_source = None
            video_file_path = check_res_at_least(url, res)

            if not video_file_path:
                audio_source = check_media(url, 'audio')
                if res_str in sources:
                    if res_str == 'audio' or res_str == 'audio_drc':
                        audio_source = audio_source or sources[res_str]
                    else:
                        video_url = sources[res_str]
                        audio_source = audio_source or sources.get('audio_drc') or sources.get('audio') or sources.get('audio_presumed')

                if not video_url and not audio_source:
                    print('Could not find any suitable streamable video format: Downloading the whole video')
                    video_file_path = download_file(url, f'video-{res}p')

            ffmpeg_command = [
                '-c:v', 'libx264',
                '-crf', '22',
                '-r', f'{meta.get("fps") or "30"}',
                '-c:a', 'aac',
                '-ar', '44100',
                '-f', 'hls',
                '-vf', f'scale=-2:{res}',
                '-force_key_frames', f'expr:gte(t,n_forced*{hls_duration})',
                '-hls_time', f'{hls_duration}',
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
                    if not video_file_path:
                        ff = FFMPEG()
                        Thread(target=ff.run, args=[ffmpeg_command]).start()
                        time.sleep(10)
                        video_file_path = download_file(url, f'video-{res}p')
                        if not video_file_path: raise RuntimeError('Could not download video')
                        ff.kill()
                        os.rename(m3u8_path, temp_m3u8_path)
                        download_file(url, media_type)
                    elif FFMPEG(ffmpeg_command).success:
                        print(f"FFMPEG Finished HLS Conversion!")
                        with open(temp_m3u8_path, 'r') as f:
                            contents = f.read()
                        with open(m3u8_path, 'w') as f:
                            f.write(contents.replace('segment', seg_path + 'segment'))
                        os.remove(temp_m3u8_path)
                    else:
                        print(f"An FFMPEG error occurred during HLS conversion")
                except Exception as e:
                    print(f"An unexpected error occurred during HLS conversion: {e}")

            Thread(target=download_hls_files, daemon=True).start()


        elif media_type.startswith('low'):
            if meta.get('is_live'): raise NotImplementedError('Livestream transcoding is not supported')
            ffmpeg_command = [
                '-i', download_file(url, 'video'),
                '-c:v', 'libx265',
                '-crf', '34',
                '-c:a', 'aac',
                '-r', '30',
                '-vf', 'scale=-2:240',
                '-preset', 'veryfast',
                os.path.join(get_data_dir(get_url(request)), 'low.mp4')
            ]
            FFMPEG(ffmpeg_command)


        elif media_type.startswith('sub'):
            lang = media_type.split('-')[1]
            print(f'downloading sub for {lang=}')

            try:
                sub = {**(meta.get('subtitles') or {}), **(meta.get('automatic_captions') or {})}.get(lang) or ''
                for i in sub:
                    if i.get('ext') == 'srt':
                        sub_url = i.get('url')
                        if sub_url:
                            download_media_file(sub_url, os.path.join(data_dir, media_type), 'srt')
                            break
                    if i.get('ext') == 'vtt':
                        sub_url = i.get('url')
                        if sub_url:
                            download_media_file(sub_url, os.path.join(data_dir, media_type), 'vtt')
                            break
                else:
                    raise FileNotFoundError('Selected subtitles not found')
                file = check_media(url=url, media_type=media_type)
                if not file:
                    raise FileNotFoundError('Selected subtitles not found')
                with open(file, 'r') as f:
                    if '-->' not in f.read():
                        raise TypeError('Downloaded subtitles are not valid')

            except Exception as e:
                print(f'Direct subtitle download did not succeed: {e}. Downloading using yt-dlp.')
                if f := check_media(url=url, media_type=media_type):
                    os.remove(f)
                ydl_opts.update({'writesubtitles': True, 'skip_download': True, 'subtitleslangs': [lang]})
                YTDLP.download(url, ydl_opts)

            file = check_media(url=url, media_type=media_type)
            if file and file.endswith('srt'):
                with open(file, 'r') as f:
                    data = f.read()
                data = re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})', r'\1.\2', data)
                with open(file, 'w') as f:
                    f.write('WEBVTT\n' + data)


        elif media_type.startswith('sprite'):
            if meta.get('is_live'): raise NotImplementedError('Livestream transcoding is not supported')
            if meta["duration"] > generate_sprite_below: raise ValueError(f"Video too long to generate sprite! ({meta["duration"]}s)")
            if not meta.get('height') and not meta.get('width'): raise TypeError('Sprite not available on non-video media!')
            video_path = check_media(url=url, media_type='video')
            sprite_dir = os.path.join(data_dir, 'temp_sprite')
            os.makedirs(sprite_dir, exist_ok=True)
            if not video_path:
                download_file(url, 'video')
                video_path = check_media(url=url, media_type='video')
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
                    if not FFMPEG(ffmpeg_command).success: raise RuntimeError('FFMPEG failed to extract sprite')
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
                    sprite_image.save(os.path.join(data_dir, 'sprite.jpg'))
                    shutil.rmtree(sprite_dir)
                except Exception as e:
                    print(f"Sprite error: {e}")

        return check_media(url=url, media_type=media_type)


def host_file(url: str, media_type='video', download_name: str | None = None):
    if not url: return jsonify({"error": "URL parameter is required"}), 400
    file = download_file(url, media_type)
    if file:
        if download_name:
            if '-' in media_type: download_name += '-' + media_type.split('-', 1)[-1]
            download_name += os.path.splitext(file)[1]
        return send_file_partial(file, download_name=download_name)
    return jsonify({"error": f"Cannot gather {media_type}"}), 404



@app.route('/')
def index():
    print('Started serving root')
    ydl_version = Downloader.get_ytdlp_version()
    ffmpeg_version = Downloader.get_ffmpeg_version(ffmpeg)
    print('Stopped serving root')
    return render_template('index.html', ydl_version=ydl_version, app_version=app_version, ffmpeg_version=ffmpeg_version, app_title=app_title, theme_color=theme_color, amoled_bg=amoled_bg)



@app.route('/watch')
def watch():
    print('Started serving watch')
    ydl_version = Downloader.get_ytdlp_version()
    ffmpeg_version = Downloader.get_ffmpeg_version(ffmpeg)
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
    return render_template('watch.html', original_url=url, ydl_version=ydl_version, app_version=app_version, ffmpeg_version=ffmpeg_version, app_title=app_title, theme_color=theme_color, generate_sprite_below=generate_sprite_below, amoled_bg=amoled_bg, video_width=video_width, video_height=video_height, video_title=video_title)


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
    return render_template('iframe.html', app_title=app_title, theme_color=theme_color, generate_sprite_below=generate_sprite_below, video_width=video_width, video_height=video_height)


@app.route('/preload')
def preload(url = None, meta = None, playlist = None):
    try:
        url = url or ((meta.get('original_url') or '') if meta else get_url(request))
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
            Thread(target=download_file, args=[url, 'thumb']).start()
        if not check_media(url, 'audio'):
            Thread(target=download_file, args=[url, 'audio']).start()
        if playlist and not check_media(url, 'playlist'):
            with open(os.path.join(get_data_dir(url), 'playlist.json'), 'w') as f:
                json.dump(playlist, f)
        return 'Preloading', 202
    except Exception as e:
        return pprint_exc(e)


@app.route('/thumb')
def serve_thumbnail():
    try:
        url = get_url(request)
        return serve_thumbnail_by_path(url)
    except Exception as e:
        return pprint_exc(e)



@app.route('/thumb/<path:url>')
def serve_thumbnail_by_path(url):
    try:
        return host_file(url, 'thumb')
    except Exception as e:
        return pprint_exc(e)


@app.route('/sprite')
def serve_sprite():
    url = get_url(request)
    return serve_sprite_by_path(url)


@app.route('/sprite/<path:url>')
def serve_sprite_by_path(url):

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
        res = (request.args.get('quality') or '').removesuffix("p")
        start_time = request.args.get('start', 0, type=float)
        end_time = request.args.get('end', 0, type=float)
        
        media_type = 'audio' if res == 'audio' else f'video-{res}p'.removesuffix('-p')
        
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


@app.route('/download/<path:filename>')
def download_ytdlp(filename):
    try:
        print('Started serving download/path')
        print(filename)
        path = (os.path.join('download', filename))
        print(f'Serving {path}')
        os.utime(path)
        print('Stopped serving download/path')
        return send_from_directory(os.path.dirname(path), os.path.basename(path))
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
        media_type = f'hls-{res}'.removesuffix('-p')
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


@app.route('/hls')
def download_hls():
    try:
        res = (request.args.get('quality') or '').removesuffix("p")    
        media_type = 'hls' if res == 'audio' else f'hls-{res}p'.removesuffix('-p')
        return host_file(get_url(request), media_type)
    except Exception as e:
        return pprint_exc(e)


@app.route('/hls_stream/<path:filename>')
def hls_stream(filename):
    base_dir = os.path.abspath(download_path)
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
def serve_search():
    try:
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
        with open(os.path.join(get_data_dir(url), 'cookies.txt'), 'w') as f:
            f.write(cookies)
        return "OK", 200

    except Exception as e:
        return pprint_exc(e)



thread = Thread(target=delete_old_files)
downloader_thread = Thread(target=ytdlp_download)
thread.start()
downloader_thread.start()



if __name__ == '__main__':
    app.run(threaded=True, host='0.0.0.0')
