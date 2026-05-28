from main import *
from flask import jsonify
from urllib.parse import unquote, urlparse, parse_qs, urlencode, urlunparse
import os
from datetime import datetime
import time
from sb import SponsorBlock
import re
from external import yt_dlp
from hashlib import sha1
import subprocess
import json
import traceback
from multiprocessing import Process, Queue



class Processes:
    @staticmethod
    def get():
        proc = {}
        for i in os.listdir(download_path):
            if not os.path.isdir(os.path.join(download_path, i)):
                with open(os.path.join(download_path, i), 'r') as f:
                    proc[str(i)] = json.load(f)
        return proc

    @staticmethod
    def getitem(item):
        with open(os.path.join(download_path, str(item)), 'r') as f:
            return json.load(f)

    @staticmethod
    def setitem(item, val):
        print(f'Assigning pid {item} to {val}')
        with open(os.path.join(download_path, str(item)), 'w') as f:
            json.dump(val, f)

    @staticmethod
    def rm(item, kill = False):
        print(f'Removing pid {item}{"(killing)" if kill else ""}')
        if kill:
            try:
                os.kill(int(item), 9)
                time.sleep(.2)
            except ProcessLookupError:
                print('Skipping killing - process already exited')
            except Exception as e:
                pprint_exc(e)
        if os.path.exists(os.path.join(download_path, str(item))):
            os.remove(os.path.join(download_path, str(item)))

    @staticmethod
    def rm_all(url = None):
        "Removes all processes for a given url (if provided) or the whole app"
        print(f'Killing all processes{" for " + url if url else ""}')
        cancelled_count = 0
        for _ in range(10):
            p = Processes.get()
            for proc in p.keys():
                try:
                    if url == p[proc][0] or url is None:
                        Processes.rm(proc, kill=True)
                        cancelled_count += 1
                except Exception as e:
                    pprint_exc(e)
            time.sleep(0.2)
        return cancelled_count



class YTDLP:

    class Logger:
        def __init__(self, url, opts, method, yt_id = None):
            self.yt_id = yt_id or sha1(f'{time.time()}'.encode()).hexdigest()[:6]
            if not yt_id: self.start(url, opts, method)

        def start(self, url, opts, method):
            print(f'[YT-DLP {self.yt_id}] Running YT-DLP {method} with opts: {opts} for url: {url}')

        def debug(self, msg):
            print(f'[YT-DLP {self.yt_id}] {msg}')

        def info(self, msg):
            print(f'[YT-DLP {self.yt_id}] {msg}')

        def warning(self, msg):
            print(f'[YT-DLP {self.yt_id}] WARNING {msg}')

        def error(self, msg):
            print(f'[YT-DLP {self.yt_id}] ERROR {msg}')
        
        def finish(self):
            print(f'[YT-DLP {self.yt_id}] Finished')


    @staticmethod
    def _ydl_runner(url, opts, with_info, arg, queue, yt_id = None):
        logger = YTDLP.Logger(url, opts, 'download', yt_id)
        try:
            with yt_dlp.YoutubeDL(opts | {'logger': logger}) as ydl:
                if with_info:
                    ydl.download_with_info_file(arg)
                else:
                    ydl.download(arg)
        except Exception as e:
            queue.put(f'{e}')
        logger.finish()


    @staticmethod
    def download(url, opts):
        if (proxy): opts["proxy"] = proxy
        logger = YTDLP.Logger(url, opts, 'download')
        def ydl_download(url, opts, with_info = False):
            q = Queue()
            arg = check_media(url, 'meta') if with_info else unquote(url)
            p = Process(target=YTDLP._ydl_runner, args=(url, opts, with_info, arg, q, logger.yt_id))
            p.start()
            Processes.setitem(p.pid, [url, f'YT-DLP {logger.yt_id}', time.time()])
            p.join()
            Processes.rm(p.pid)
            while not q.empty():
                logger.error(q.get())
            logger.info(f'Exited with code {p.exitcode}')
            if p.exitcode != 0: raise RuntimeError(f'YT-DLP exited unexpectedly with return code {p.exitcode}')

        try:
            try:
                ydl_download(url, opts, True)
            except Exception as e:
                pprint_exc(e)
                logger.error('An error occured when downloading with meta. Downloading without meta...')
                ydl_download(url, opts, False)
        except Exception as e:
            if (cookies := get_global_cookies_file(True)):
                pprint_exc(e)
                logger.error('An error occured when downloading. Downloading with cookies...')
                opts["cookiefile"] = cookies
                opts["mark_watched"] = False
                ydl_download(url, opts)
            else:
                logger.error('An error occured when downloading. Providing cookies may help with this issue.')
                raise e
        finally:
            logger.finish()


    @staticmethod
    def get_info(url, opts):
        if (proxy): opts["proxy"] = proxy
        logger = YTDLP.Logger(url, opts, 'extract_info')
        try:
            with yt_dlp.YoutubeDL(json.loads(json.dumps(opts)) | {'logger': logger}) as ydl:
                return ydl.sanitize_info(ydl.extract_info(url, download=False))
        except Exception as e:
            if (cookies := get_global_cookies_file(True)):
                pprint_exc(e)
                logger.error('An error occured when downloading. Downloading with cookies...')
                opts["cookiefile"] = cookies
                opts["mark_watched"] = False
                logger.start(url, opts, 'extract_info')
                with yt_dlp.YoutubeDL(opts | {'logger': logger}) as ydl:
                    return ydl.sanitize_info(ydl.extract_info(url, download=False))
            else:
                logger.error('An error occured when downloading. Providing cookies may help with this issue.')
                raise e
        finally:
            logger.finish()



class FFMPEG:
    def __init__(self, url, ffmpeg_command=None):
        """
        Provide ffmpeg_command to run synchronously. Check with `success`
        """
        self._p = None
        self.pid = None
        self.ffmpeg = ffmpeg
        self.ff_id = sha1(f'{time.time()}'.encode()).hexdigest()[:6]
        self.success = False
        self.start_time = time.time()
        self.url = url
        if ffmpeg_command and self.ffmpeg:
            self.run(ffmpeg_command)

    def kill(self):
        if self._p is None: return
        Processes.rm(self.pid, kill=True)
        print(f'[FFMPEG {self.ff_id}] Killed')

    def run(self, ffmpeg_command):
        """
        Also runs synchronously, but can be placed in `Thread`
        """
        if not self.ffmpeg: return None
        ffmpeg_command = [self.ffmpeg] + ffmpeg_command
        ffmpeg_env = {f"{proxy.split('://')[0]}_proxy": proxy} if proxy else None
        print(f'[FFMPEG {self.ff_id}] Executing {ffmpeg_command}')
        self._p = subprocess.Popen(ffmpeg_command, stdout = subprocess.PIPE, stderr = subprocess.STDOUT, env=ffmpeg_env)
        self.pid = self._p.pid
        Processes.setitem(self.pid, [self.url, f'FFMPEG {self.ff_id}', time.time()])
        for line in self._p.stdout:
            print(f'[FFMPEG {self.ff_id}] {line.decode().strip()}')
            if time.time() - self.start_time > 3600:
                self.kill()
                self.success = False
                raise TimeoutError()
        self._p.wait()
        Processes.rm(self.pid)
        print(f'[FFMPEG {self.ff_id}] Finished')
        self.success = True



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



def pprint_exc(e, code = 500):
    error = (re.sub(r'[^\x20-\x7e]',r'', re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", str(e))))
    traceback.print_exception(e)
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


def keepalive(data_dir):
    with open(os.path.join(data_dir, 'keepalive'), 'w') as f:
        f.write(str(int(time.time())))


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


def get_meta(url: str):
    with FileCachingLock(url, 'meta') as cache:
        print(cache)
        if cache:
            try:
                with open(cache, 'r') as f: return json.load(f)
            except:
                print('Meta file invalid - Regenerating...')
        print(f'downloading meta for {url}')
        ydl_opts = {'skip_download': True}
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
        video_name = ''
        audio_name = ''
        if (f.get('vcodec') or 'none').lower() != 'none' or ((f.get('video_ext') or 'none').lower() != 'none'):
            video_name = f"{(f.get('height') or '')}"
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
    preferred_quality = get_good_quality(get_video_formats(url, protocol='https'))
    for s in sources:
        if s.startswith(f'{preferred_quality}audio'):
            return sources[s]
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
    del ydl_opts['playlistend']
    info = YTDLP.get_info(query, ydl_opts)
    entries = info.get('entries') or []
    for entry in entries:
        entry['original_url'] = normalize_url(append_query_to_url(entry['original_url'], query))
    return entries


def generate_chapters(meta: dict):
    chapters = []
    try:
        meta_chapters = meta.get('chapters') or []
        for chapter in meta_chapters:
            chapters.append({'time': chapter.get('start_time'), 'label': chapter.get('title')})
        if chapters: return chapters
    except: pass
    try:
        desc = meta.get('description')
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
    meta['generate_sprite_below'] = generate_sprite_below
    meta['hls_duration'] = hls_duration
    meta['hls_audio_duration'] = hls_audio_duration
    meta['playlist_support'] = playlist_support
    meta['auto_bg_playback'] = auto_bg_playback
    meta['audio_visualizer'] = audio_visualizer
    meta['autoskip_sb_segments'] = autoskip_sb_segments
    meta['chapters'] = generate_chapters(raw_meta)
    if raw_meta.get('is_live'):
        meta['formats'] = []
        meta['load_default_quality'] = False
        meta['subtitles'] = []
        meta['duration'] = '0'
    return meta


def normalize_url(url):
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    strip_query = ['pp', 'themeRefresh', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'fbclid', 'igshid', 'srcid']
    for i in strip_query:
        if i in query_params.keys():
            del query_params[i]

    new_query = urlencode(query_params, doseq=True)
    url = urlunparse(parsed_url._replace(query=new_query))

    if '.' not in url:
        url = 'https://youtube.com/watch?v=' + url
    if '/watch?v=' in url and not 'youtube.' in url.split('/watch?v=')[0]:
        yt_url = 'https://youtube.com/watch?v=' + url.split('/watch?v=')[1]
        try:
            if get_meta(yt_url):
                url = yt_url
        except: pass
    return url


def get_url(req):
    if demo := (os.environ.get('DEMO_VIDEO')): return demo
    url = req.args.get('v') or req.args.get('url') or None
    if url is None or len(url) < 3: return None
    return normalize_url(url)


def append_query_to_url(url, query):
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    query_params['q'] = query
    new_query_string = urlencode(query_params, doseq=True)
    return urlunparse(parsed_url._replace(query=new_query_string))


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
