import http.cookies
import json
import math
import mimetypes
import os
import re
import subprocess
import time
import traceback
import io
import requests
import shutil
import struct
from PIL import Image
from datetime import datetime
from hashlib import sha1
from multiprocessing import Process, Queue
from urllib.parse import parse_qs, quote_plus, unquote, urlencode, urljoin, urlparse, urlunparse
from flask import Response, jsonify, request, send_file

from external import yt_dlp
from main import *
from sb import SponsorBlock



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
        self.affected_files = []
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
        if self._p.returncode != 0:
            self.success = False
            for file in self.affected_files:
                if os.path.exists(file): os.remove(file)
            raise RuntimeError(f'FFMPEG exited unexpectedly with return code {self._p.returncode}')
        print(f'[FFMPEG {self.ff_id}] Finished')
        self.success = True



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
            elif self.media_type.startswith('audio'): self.audio()
            elif self.media_type.startswith('video'): self.video()
            elif self.media_type.startswith('hls'): self.hls()
            elif self.media_type.startswith('direct'): self.direct()
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
        selected_res = re.search(r'(\d+)', self.media_type) and re.search(r'(\d+)', self.media_type).group(1)
        self.res = int(selected_res or get_good_quality(get_video_formats(meta=self.meta)))

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
            entries.append(get_video_info(entry))
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
        hls_url_dir = os.path.join(gen_pathname(self.url), f"hls_segment-{res_str}")
        hls_output_dir = os.path.join(download_path, hls_url_dir)
        hls_segment_duration = hls_audio_duration if res_str == 'audio' else hls_duration
        os.makedirs(hls_output_dir, exist_ok=True)

        temp_m3u8_path = os.path.join(self.data_dir, f'{self.media_type}.m3u8.temp')
        m3u8_path = os.path.join(self.data_dir, f'{self.media_type}.m3u8')

        sources = get_video_sources(self.url)
        video_source = None
        audio_source = None
        video_file_path = check_media(self.url, 'audio') if res_str == 'audio' else check_res_at_least(self.url, self.res)

        if not video_file_path:
            audio_media = check_media(self.url, 'audio')
            audio_source = [audio_media] if audio_media else None
            if res_str in sources.keys():
                if res_str == 'audio':
                    audio_source = audio_source or sources[res_str]
                else:
                    video_source = sources[res_str]
                    audio_source = audio_source or sources.get('audio_drc') or sources.get('audio') or sources.get('audio_presumed')

            if not video_source and not audio_source:
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

        if video_source:
            ffmpeg_command = ['-i', video_source[0]] + ffmpeg_command
        if audio_source:
            ffmpeg_command = ['-i', audio_source[0]] + ffmpeg_command
        if video_file_path:
            ffmpeg_command = ['-i', video_file_path] + ffmpeg_command

        seg_time = 0
        seg_num = 0
        duration = self.meta["duration"]
        hls_url_dir = os.path.join(gen_pathname(self.url), f"hls_segment-{res_str}")
        seg_path = f"/hls_segment?url={quote_plus(self.url)}&quality={res_str}&seg="

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
                    ff.affected_files = [m3u8_path, temp_m3u8_path]
                    Thread(target=ff.run, args=[ffmpeg_command]).start()
                    time.sleep(2)
                    video_file_path = MediaDownloader(self.url, 'audio' if 'audio' in self.media_type else f'video-{self.res}').run()
                    if not video_file_path: raise RuntimeError('Could not download video')
                    print(f'Killing FFMPEG {ff.ff_id} due to local media availability')
                    ff.kill()
                    if os.path.exists(m3u8_path): os.rename(m3u8_path, temp_m3u8_path)
                    MediaDownloader(self.url, self.media_type).run()
                else:
                    ff = FFMPEG(self.url, ffmpeg_command)
                    ff.affected_files = [m3u8_path, temp_m3u8_path]
                    if ff.success:
                        print(f"FFMPEG Finished HLS Conversion!")
                        if os.path.exists(temp_m3u8_path): os.remove(temp_m3u8_path)
                    else:
                        print(f"An FFMPEG error occurred during HLS conversion")
            except Exception as e:
                print(f"An unexpected error occurred during HLS conversion")
                pprint_exc(e)

        Thread(target=download_hls_files, daemon=True).start()


    def direct(self):
        get_direct(self.url, self.meta, self.res if 'audio' not in self.media_type else None)


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
        if get_sprite(self.url, self.meta): return
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


def load_http_cookies(cookies_str):
    if not cookies_str: return None
    c = http.cookies.SimpleCookie()
    c.load(cookies_str)
    return requests.utils.cookiejar_from_dict({k: v.value for k, v in c.items()})


def stream_media_file(url: str, headers: str|None = None, cookies: str|None = None):
    """Stream raw file with requests.get"""
    try:
        headers_dict = json.loads(headers) if headers else {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        if client_range := request.headers.get('Range'):
            headers_dict['Range'] = client_range
        response = requests.get(url, stream=True, headers=headers_dict, cookies=load_http_cookies(cookies))
        response.raise_for_status()
        mime_type = response.headers.get('Content-Type', 'application/octet-stream')

        if 'mpegurl' in mime_type.lower():
            lines = []
            url_regex = re.compile(r'(URI=["\'])([^"\']*)(["\'])')

            def replace_url(match):
                prefix, orig_url, suffix = match.groups()
                new_url = f'/external?url={quote_plus(urljoin(url, orig_url))}&headers={quote_plus(headers)}&cookies={quote_plus(cookies)}'
                return f'{prefix}{new_url}{suffix}'
            
            for line in response.content.decode('utf-8', errors='ignore').splitlines():
                line_str = line.strip()
                if not line_str:
                    lines.append(line)
                    continue

                if line_str.startswith('#'):
                    lines.append(url_regex.sub(replace_url, line))
                else:
                    lines.append(f'/external?url={quote_plus(urljoin(url, line_str))}&headers={quote_plus(headers)}&cookies={quote_plus(cookies)}')

            resp = Response('\n'.join(lines), status=response.status_code, mimetype=mime_type)
            return resp

        def generate():
            for chunk in response.iter_content(chunk_size=8192):
                yield chunk

        resp = Response(generate(), status=response.status_code, mimetype=mime_type)

        if 'Content-Length' in response.headers:
            resp.headers['Content-Length'] = response.headers['Content-Length']
        if 'Content-Range' in response.headers:
            resp.headers['Content-Range'] = response.headers['Content-Range']
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



def host_file(url: str, media_type='video', download_name: str | None = None):
    if not url: return jsonify({"error": "URL parameter is required"}), 400
    file = MediaDownloader(url, media_type).run()
    if file:
        if download_name:
            if '-' in media_type: download_name += '-' + media_type.split('-', 1)[-1]
            download_name += os.path.splitext(file)[1]
        return send_file_partial(file, download_name=download_name)
    return jsonify({"error": f"Cannot gather {media_type}"}), 404



def preload(url = None, meta = None, playlist = None):
    url = url or (meta.get('original_url') or '')
    print('Running preload')

    if meta:
        if meta.get('entries'): meta = meta['entries'][0]
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
        if info.get('entries'): info = info['entries'][0]
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


def get_video_formats(url = None, meta = None, protocols = None, exts = []):
    """
    Generates a list of all resolutions for video
    """
    return sorted(list(set(int(i.split('a')[0]) for i in get_video_sources(url, meta, protocols, exts).keys() if i.split('a')[0])))


def get_video_sources(url = None, meta = None, protocols = [], exts = []):
    """
    Aggregates all possible sources for video

    Returns:
        dict[res, List[url, headers, cookies, codec]]
    """
    sources = {}
    best_audio = 0
    meta = meta or get_meta(url)
    formats = meta.get('formats') or []
    language = meta.get('language')
    formats.sort(key=lambda f: f.get('source_preference') or 0, reverse=True)
    for f in formats:
        video_name = ''
        audio_name = ''
        if language and f.get('language') and (f.get('language') != language): continue
        if (f.get('vcodec') or 'none').lower() != 'none' or ((f.get('video_ext') or 'none').lower() != 'none'):
            video_name = f"{(f.get('height') or '')}"
        if f.get('acodec', 'none') != 'none':
            audio_name = 'audio_drc' if 'drc' in f"{f.get('format_id')} {f.get('format_note')}".lower() else 'audio'
        if 'audio' in (f.get('format_id') or '') or (f.get('acodec') or 'audio_presumed') == 'audio_presumed':
            audio_name = 'audio_presumed'
        name = video_name + audio_name
        quality = float(f.get('quality') or 0)
        if not name: continue
        if protocols and f.get('protocol') not in protocols: continue
        if exts and f.get('ext') not in exts: continue

        if name.startswith('audio') and quality < best_audio:
            best_audio = quality
        if name not in sources:
            headers = json.dumps(f.get('http_headers') or {})
            cookies = f.get('cookies') or ''
            codec = f.get('vcodec') if name[0] != 'a' else f.get('acodec')
            sources[name] = [f['url'], headers, cookies, codec]
    return sources


def check_res_at_least(url:str, res: int):
    for f in get_video_formats(url):
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


def generate_hls(audio_source, video_source):

    get_url = lambda s: f'/external?url={quote_plus(s[0])}&headers={quote_plus(s[1])}&cookies={quote_plus(s[2])}'

    audio_url = get_url(audio_source) if audio_source and audio_source != video_source else None
    video_url = get_url(video_source) if video_source else None

    return '\n'.join([
        '#EXTM3U',
        '#EXT-X-VERSION:3',
        f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio_grp",NAME="English",DEFAULT=YES,AUTOSELECT=YES,URI="{audio_url}"' if audio_url and video_url else "",
        f'#EXT-X-STREAM-INF:BANDWIDTH=1500000{",AUDIO=\"audio_grp\"" if audio_url and video_url else ""}',
        f'{video_url}' if video_url else f'{audio_url}'
    ])


def generate_dash(audio_source, video_source, duration):
    def get_mp4_dash_ranges(source):
        headers_dict = json.loads(source[1]) | {"Range": "bytes=0-60000"}
        response = requests.get(source[0], headers=headers_dict, cookies=load_http_cookies(source[2]))
        response.raise_for_status()
        data = response.content
        offset = 0

        while offset < len(data):
            if offset + 8 > len(data): break

            box_size, box_type = struct.unpack(">I4s", data[offset : offset + 8])

            if box_size == 1:
                if offset + 16 > len(data): break
                box_size = struct.unpack(">Q", data[offset + 8 : offset + 16])[0]

            # The 'sidx' box contains the segment index map required by DASH
            if box_type.decode("utf-8", errors="ignore") == "sidx":
                return f"0-{offset - 1}", f"{offset}-{offset + box_size - 1}"

            if box_size == 0: break
            offset += box_size

        raise ValueError('Could not locate sidx box')

    mpd_src = lambda src, ranges, mediatype: '\n'.join([
       f'        <AdaptationSet mimeType="{mediatype}/mp4" codecs="{src[3]}" subsegmentAlignment="true" subsegmentStartsWithSAP="1">',
       f'          <Representation id="{mediatype}_track" bandwidth="1000000">',
       f'            <BaseURL><![CDATA[/external?url={quote_plus(src[0])}&headers={quote_plus(src[1])}&cookies={quote_plus(src[2])}]]></BaseURL>',
       f'            <SegmentBase indexRange="{ranges[1]}" indexRangeExact="true">',
       f'              <Initialization range="{ranges[0]}" />',
        '            </SegmentBase>',
        '          </Representation>',
        '        </AdaptationSet>'
    ]) if src else ''

    return '\n'.join([
        '<?xml version="1.0" encoding="utf-8"?>',
        '<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" '
        '    profiles="urn:mpeg:dash:profile:isoff-on-demand:2011" ',
        '    type="static"',
       f'    mediaPresentationDuration="PT{float(duration):.3f}S">',
        '    <Period>',
        mpd_src(video_source, get_mp4_dash_ranges(video_source), 'video'),
        mpd_src(audio_source, get_mp4_dash_ranges(audio_source), 'audio'),
        '    </Period>',
        '</MPD>'
    ])


def choose_sources_for_res(sources: dict, res = None):
    """
    Chooses (audio_source, video_source) among sources, needed for playback with specific resolution.
    """
    res = str(res) if res else ''
    video_source = None
    audio_source = None
    for s in sources.keys():
        if not audio_source and 'audio' in s: audio_source = s
        if res and not video_source and res in s:
            video_source = s
        if 'audio' in s and res in s:
            audio_source = s
            video_source = s
            break
    if (video_source or not res) and audio_source:
        return sources.get(audio_source) or None, sources.get(video_source) or None
    return [], []


def get_direct(url = None, meta = None, res = None, simulate = False):

    sources = get_video_sources(url, meta, protocols=['http', 'https'])
    a, v = choose_sources_for_res(sources, res)
    if a and (not res or a == v):
        if not simulate:
            with open(os.path.join(get_data_dir(url), f'direct-{res or "audio"}.url'), 'w') as f:
                f.write(a[0] + '\n' + a[1] + '\n' + a[2])
        return 'video/mp4' if res else 'audio/mpeg'

    sources = get_video_sources(url, meta, protocols=['m3u8_native'])
    a, v = choose_sources_for_res(sources, res)
    if a or v:
        if not simulate:
            print(f'Generating HLS direct for {res}')
            try:
                content = generate_hls(a, v)
                with open(os.path.join(get_data_dir(url), f'direct-{res or "audio"}.m3u8'), 'w') as f:
                    f.write(content)
            except Exception as e:
                pprint_exc(e)
        return 'application/x-mpegURL'

    sources = get_video_sources(url, meta, protocols=['http', 'https'], exts=['mp4', 'm4a'])
    a, v = choose_sources_for_res(sources, res)
    if a or v:
        if not simulate:
            print(f'Generating MPD direct for {res}')
            try:
                content = generate_dash(a, v, meta['duration'])
                with open(os.path.join(get_data_dir(url), f'direct-{res or "audio"}.mpd'), 'w') as f:
                    f.write(content)
            except Exception as e:
                pprint_exc(e)
        return 'application/dash+xml'
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


def get_sprite(url = None, meta = None, simulate = False):
    """[width, height, columns, duration]"""
    try:
        format = None
        formats = meta.get('formats') or []
        formats.sort(key=lambda f: f.get('width') or 0)

        for f in formats:
            if not f.get('columns'): continue
            format = f
            if (f.get('width') or 0) >= 150 or (f.get('height') or 0) >= 150: break

        if not simulate:
            image_urls = []
            if format.get('fragments'):
                for fragment in format['fragments']:
                    image_urls.append(fragment['url'])
            else:
                image_urls.append(format['url'])

            downloaded_images = []
            width = 0
            height = 0

            for i, img_url in enumerate(image_urls):
                response = requests.get(img_url)
                response.raise_for_status()
                img = Image.open(io.BytesIO(response.content))

                if i == 0: width = img.width
                height += img.height

                downloaded_images.append(img)

            final_sprite = Image.new('RGB', (width, height))
            current_y = 0
            for img in downloaded_images:
                final_sprite.paste(img, (0, current_y))
                current_y += img.height

            final_sprite.save(os.path.join(get_data_dir(url), 'sprite.jpg'))

        return [format['width'], format['height'], format['columns'], 1 / format['fps']]
    except Exception as e:
        pprint_exc(e)
        return None


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


def get_video_info(meta: dict):
    info = {}
    info['title'] = meta.get('title') or ''
    info['uploader'] = meta.get('uploader') or ''
    try:
        info['formats'] = get_video_formats(meta=meta)
    except BaseException as e:
        info['formats'] = jsonify({'error': (re.sub(r'[^\x20-\x7e]',r'', re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", str(e))))}), 403
    info['sources'] = {}
    for res in info['formats'] + [0]:
        src = get_direct(meta=meta, res=res, simulate=True)
        if src: info['sources'][str(res or 'audio')] = src
    info['duration'] = f'{meta.get("duration") or 0}'
    info['subtitles'] = get_subtitles(meta)
    info['width'] = meta.get('width')
    info['height'] = meta.get('height')
    info['url'] = meta.get('original_url')
    info['default_quality'] = 'audio' if 'Music' in (meta.get('categories') or []) and audio_visualizer else get_good_quality(info['formats'])
    info['always_transcode'] = always_transcode
    info['generate_sprite_below'] = generate_sprite_below
    info['hls_duration'] = hls_duration
    info['hls_audio_duration'] = hls_audio_duration
    info['playlist_support'] = playlist_support
    info['auto_bg_playback'] = auto_bg_playback
    info['audio_visualizer'] = audio_visualizer
    info['autoskip_sb_segments'] = autoskip_sb_segments
    info['chapters'] = generate_chapters(meta)
    info['sprite'] = get_sprite(info['url'], meta, True) or [160, 90, 10, 10]
    if meta.get('is_live'):
        info['subtitles'] = []
        info['duration'] = '0'
    return info


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
