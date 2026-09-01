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
from queue import Empty
from PIL import Image
from datetime import datetime
from hashlib import sha1
from multiprocessing import Process, Queue
from urllib.parse import parse_qs, quote_plus, unquote, urlencode, urljoin, urlparse, urlunparse
from flask import Response, jsonify, request, send_file
from external import External
from main import *
from sb import SponsorBlock

yt_dlp = External.yt_dlp()


class CacheLockStore:
    """Filesystem store for cache-job and media-generation locks."""

    def __init__(self, url, media_type):
        self.data_dir = get_data_dir(url)
        self.media_lock_path = os.path.join(self.data_dir, f'{media_type}.temp')
        self.job_lock_path = os.path.join(self.data_dir, f'{media_type}.cache-start.temp')

    @staticmethod
    def _try_acquire(path, cleanup_on_error=False):
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            return False

        try:
            with os.fdopen(descriptor, 'w') as lock_file:
                lock_file.write(datetime.now().isoformat())
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            if cleanup_on_error:
                CacheLockStore._release(path)
            raise
        return True

    @staticmethod
    def _release(path):
        try:
            os.remove(path)
            return True
        except FileNotFoundError:
            return False

    def media_lock_exists(self):
        return os.path.exists(self.media_lock_path)

    def job_lock_exists(self):
        return os.path.exists(self.job_lock_path)

    def any_lock_exists(self):
        return self.media_lock_exists() or self.job_lock_exists()

    def try_acquire_media_lock(self):
        os.makedirs(self.data_dir, exist_ok=True)
        return self._try_acquire(self.media_lock_path, cleanup_on_error=True)

    def try_acquire_job_lock(self):
        os.makedirs(self.data_dir, exist_ok=True)
        return self._try_acquire(self.job_lock_path)

    def release_media_lock(self):
        return self._release(self.media_lock_path)

    def release_job_lock(self):
        return self._release(self.job_lock_path)

    def remove_stale_job_lock(self, max_age):
        if not self.job_lock_exists() or self.media_lock_exists():
            return False
        try:
            if time.time() - os.path.getmtime(self.job_lock_path) <= max_age:
                return False
        except FileNotFoundError:
            return False
        return self.release_job_lock()


class FileCachingLock:
    max_wait_attempts = 600
    retry_interval_seconds = 1

    def __init__(self, url, media_type):
        self.url = url
        self.media_type = media_type
        self.store = CacheLockStore(url, media_type)
        self.data_dir = self.store.data_dir
        self.lock_path = self.store.media_lock_path
        self.acquired = False

    def __enter__(self):
        for attempt in range(self.max_wait_attempts):
            if not self.store.try_acquire_media_lock():
                if attempt == self.max_wait_attempts - 1:
                    raise TimeoutError(
                        f'Timed out waiting for download of {self.media_type} '
                        f'for {os.path.basename(self.data_dir)}'
                    )
                print(f'Waiting for download of {self.media_type} for {os.path.basename(self.data_dir)}')
                time.sleep(self.retry_interval_seconds)
                continue

            self.acquired = True
            try:
                keepalive(self.data_dir)
                if cached_media := check_media(url=self.url, media_type=self.media_type):
                    if is_compatible_cached_media(cached_media, self.media_type):
                        print(f'Cache hit for {self.media_type}!')
                        return cached_media
                    print(f'Removing incompatible cached media: {cached_media}')
                    try:
                        os.remove(cached_media)
                    except FileNotFoundError:
                        pass
                return None
            except Exception:
                self._release()
                raise

    def _release(self):
        if not self.acquired:
            return
        try:
            if not self.store.release_media_lock():
                print(f'FATAL ERROR trying to unlock {self.media_type} of {self.data_dir}. Media type cannot be downloaded')
        finally:
            self.acquired = False

    def __exit__(self, exc_type, exc_value, traceback):
        self._release()



class Processes:
    @staticmethod
    def get():
        proc = {}
        try:
            for i in os.listdir(data_path):
                if not os.path.isdir(os.path.join(data_path, i)):
                    with open(os.path.join(data_path, i), 'r') as f:
                        proc[str(i)] = json.load(f)
        except: pass
        return proc

    @staticmethod
    def getitem(item):
        with open(os.path.join(data_path, str(item)), 'r') as f:
            return json.load(f)

    @staticmethod
    def setitem(item, val):
        print(f'Assigning pid {item} to {val}')
        proc = Processes.get()
        if len(proc.keys()) > max_processes:
            oldest = min(proc, key=lambda k: proc[k][2])
            print('Too many processes! Killing the oldest one')
            Processes.rm(oldest, True)
        with open(os.path.join(data_path, str(item)), 'w') as f:
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
        if os.path.exists(os.path.join(data_path, str(item))):
            os.remove(os.path.join(data_path, str(item)))

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



class DownloadProgress:
    """Persists download progress so it can be read by any web worker."""

    update_interval = 0.2
    ffmpeg_postprocessors = {
        'ExtractAudio',
        'Merger',
        'VideoConvertor',
        'VideoRemuxer',
    }

    def __init__(self, url: str, progress_id: str | None):
        self.url = url
        self.progress_id = progress_id if self.valid_id(progress_id) else None
        self.path = self.get_path(url, self.progress_id) if self.progress_id else None
        self.last_write = 0
        self.state = self.initial_state()

    @staticmethod
    def initial_state():
        return {
            'status': 'preparing',
            'percent': 0,
            'downloaded_bytes': 0,
            'total_bytes': 0,
            'speed': 0,
        }

    @staticmethod
    def valid_id(progress_id):
        return isinstance(progress_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,80}', progress_id) is not None

    @staticmethod
    def get_path(url, progress_id):
        return os.path.join(get_data_dir(url), f'download-progress-{progress_id}.json')

    @classmethod
    def read(cls, url, progress_id):
        if not cls.valid_id(progress_id): return None
        try:
            with open(cls.get_path(url, progress_id), 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _write(self, force=False):
        if not self.path: return
        now = time.time()
        if not force and now - self.last_write < self.update_interval: return

        self.last_write = now
        self.state['timestamp'] = now
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        temp_path = f'{self.path}.{os.getpid()}.{time.time_ns()}.temp'
        try:
            with open(temp_path, 'w') as f:
                json.dump(self.state, f)
            os.replace(temp_path, self.path)
        finally:
            if os.path.exists(temp_path): os.remove(temp_path)

    def start(self):
        self._write(force=True)

    @staticmethod
    def number(value, default=0):
        try:
            value = float(value)
            return value if math.isfinite(value) and value >= 0 else default
        except (TypeError, ValueError):
            return default

    def download(self, data):
        previous_status = self.state.get('status')
        downloaded = self.number(data.get('downloaded_bytes'))
        total = self.number(
            data.get('total_bytes')
            or data.get('total_bytes_estimate')
            or data.get('filesize')
            or data.get('filesize_approx')
        )
        speed = self.number(data.get('speed'), self.state.get('speed', 0))
        status = data.get('status')

        if not total:
            fragment_index = self.number(data.get('fragment_index'))
            fragment_count = self.number(data.get('fragment_count'))
            if fragment_index and fragment_count:
                total = downloaded * fragment_count / fragment_index

        if status == 'finished':
            total = max(total, downloaded)
            percent = 100
        elif total:
            total = max(total, downloaded)
            percent = min(100, downloaded / total * 100)
        else:
            percent = 0

        self.state.update({
            'status': 'downloading',
            'percent': percent,
            'downloaded_bytes': downloaded,
            'total_bytes': total,
            'speed': speed,
        })
        self._write(force=status == 'finished' or previous_status != 'downloading')

    def handle_ytdlp_event(self, event):
        if event.get('type') == 'download':
            self.download(event)
            return

        postprocessor = event.get('postprocessor') or ''
        # HLS downloads commonly run a FixupM3u8 postprocessor after the video
        # fragments finish. That is not the final audio/video cache merge, so it
        # must not make the UI claim that the completed video is being encoded.
        is_ffmpeg = postprocessor in self.ffmpeg_postprocessors
        if event.get('type') == 'postprocessor' and event.get('status') == 'started' and is_ffmpeg:
            self.encoding()

    def _transition(self, **changes):
        self.state.update(changes)
        self._write(force=True)

    def encoding(self):
        self._transition(status='encoding', percent=100, speed=0)

    def ready(self, file_size):
        file_size = self.number(file_size)
        self._transition(
            status='ready',
            percent=100,
            downloaded_bytes=file_size,
            total_bytes=file_size,
            speed=0,
        )

    def error(self, message):
        self._transition(status='error', message=str(message), speed=0)



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
        def progress_hook(data):
            info = data.get('info_dict') or {}
            queue.put({
                'type': 'download',
                'status': data.get('status'),
                'downloaded_bytes': data.get('downloaded_bytes'),
                'total_bytes': data.get('total_bytes'),
                'total_bytes_estimate': data.get('total_bytes_estimate'),
                'speed': data.get('speed'),
                'fragment_index': data.get('fragment_index'),
                'fragment_count': data.get('fragment_count'),
                'filesize': info.get('filesize'),
                'filesize_approx': info.get('filesize_approx'),
            })

        def postprocessor_hook(data):
            queue.put({
                'type': 'postprocessor',
                'status': data.get('status'),
                'postprocessor': data.get('postprocessor'),
            })

        try:
            if ffmpeg: os.environ['PATH'] += os.path.dirname(ffmpeg)
            if js_runtime: os.environ['PATH'] += os.path.dirname(js_runtime)
            runner_opts = opts | {'logger': logger}
            runner_opts['progress_hooks'] = [*(runner_opts.get('progress_hooks') or []), progress_hook]
            runner_opts['postprocessor_hooks'] = [*(runner_opts.get('postprocessor_hooks') or []), postprocessor_hook]
            with yt_dlp.YoutubeDL(runner_opts) as ydl:
                if with_info:
                    ydl.download_with_info_file(arg)
                else:
                    ydl.download(arg)
        except Exception as e:
            queue.put({'type': 'error', 'message': f'{e}'})
            raise
        finally:
            logger.finish()


    @staticmethod
    def download(url, opts, progress_callback=None):
        if (proxy): opts["proxy"] = proxy
        logger = YTDLP.Logger(url, opts, 'download')
        def ydl_download(url, opts, with_info = False):
            q = Queue()
            arg = check_media(url, 'meta') if with_info else unquote(url)
            p = Process(target=YTDLP._ydl_runner, args=(url, opts, with_info, arg, q, logger.yt_id))
            p.start()
            Processes.setitem(p.pid, [url, f'YT-DLP {logger.yt_id}', time.time()])
            errors = []

            def handle_message(message):
                if message.get('type') == 'error':
                    errors.append(message.get('message'))
                elif progress_callback:
                    progress_callback(message)

            while p.is_alive():
                try:
                    handle_message(q.get(timeout=0.1))
                except Empty:
                    continue
            p.join()
            Processes.rm(p.pid)
            while True:
                try:
                    handle_message(q.get_nowait())
                except Empty:
                    break
            for error in errors:
                logger.error(error)
            logger.info(f'Exited with code {p.exitcode}')
            if errors: raise RuntimeError(errors[-1])
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
        if js_runtime: os.environ['PATH'] += os.path.dirname(js_runtime)
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
        self.stdout = ''
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
            line_out = line.decode().strip()
            print(f'[FFMPEG {self.ff_id}] {line_out}')
            self.stdout += line_out + '\n'
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
    def __init__(self, url: str, media_type: str, progress: DownloadProgress | None = None):
        self.url = re.sub(r'(https?):/{1,}', r'\1://', url)
        self.data_dir = get_data_dir(self.url)
        self.media_type = media_type
        self.progress = progress
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
        quality_match = re.match(r'video-(best|\d+)', self.media_type)
        self.cache_quality = quality_match.group(1) if quality_match else None
        selected_res = self.cache_quality if self.cache_quality and self.cache_quality.isdigit() else None
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
        thumb_url = self.meta.get('thumbnail')
        video_width = self.meta.get('width')
        video_height = self.meta.get('height')
        if thumb_url:
            try:
                download_media_file(thumb_url, os.path.join(self.data_dir, 'thumb-orig'))
            except Exception as e:
                pprint_exc(e)

        thumb_file = check_media(url=self.url, media_type='thumb-orig')
        if not thumb_file:
            print('Direct thumbnail download did not succeed. Downloading using yt-dlp.')
            self.ydl_opts.update({'writethumbnail': True, 'skip_download': True})
            YTDLP.download(self.url, self.ydl_opts)
            thumb_file = check_media(url=self.url, media_type='thumb-orig')

            if not thumb_file:
                print('Thumbnail download did not succeed. Generating from video.')
                try:
                    src = check_media(self.url, 'video')
                    if not src:
                        srcs = choose_sources_for_res(get_video_sources(self.url, self.meta), get_good_quality(get_video_formats(self.url, self.meta)))
                    duration = int(self.meta.get('duration') or 10)
                    ffmpeg_command = [
                        '-ss', f'{int(duration/10)}',
                        '-i', srcs[1][0],
                        '-frames:v', '1',
                        os.path.join(self.data_dir, 'thumb-orig.jpg')
                    ]
                    FFMPEG(self.url, ffmpeg_command)
                except Exception as e:
                    pprint_exc(e)
                thumb_file = check_media(url=self.url, media_type='thumb-orig')

        if not thumb_file: raise RuntimeError("No thumbnail could be generated or found.")

        try:
            if video_width and video_height:

                with Image.open(thumb_file) as im:
                    im = im.convert("RGB")

                    in_w, in_h = im.size
                    target_ar = video_width / video_height
                    if in_w / in_h > target_ar:
                        new_w = int(in_h * target_ar)
                        new_h = in_h
                    else:
                        new_h = int(in_w / target_ar)
                        new_w = in_w

                    left = (in_w - new_w) // 2
                    top = (in_h - new_h) // 2
                    right = left + new_w
                    bottom = top + new_h

                    im = im.crop((left, top, right, bottom))
                    im.save(os.path.join(self.data_dir, 'thumb.jpg'), quality=95)

                print(f"Thumbnail cropped using PIL")
                os.remove(thumb_file)
            else:
                print("Video dimensions not found in meta, skipping thumbnail cropping.")
        except Exception as e:
            print(f"Error cropping thumbnail")
            pprint_exc(e)


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
        self.ydl_opts.update({
            "format": "bestaudio/best",
            "outtmpl": os.path.join(self.data_dir, f'{self.media_type}.%(ext)s'),
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
        })
        cache_audio_progress = DownloadProgress(self.url, CACHE_AUDIO_PROGRESS_ID)
        cache_audio_progress.start()

        def handle_audio_progress(event):
            # Audio extraction is still part of preparing the cache inputs. Only
            # publish byte-download events here; the final merge sets encoding.
            if event.get('type') == 'download':
                cache_audio_progress.download(event)
            if self.progress and self.progress.progress_id != CACHE_AUDIO_PROGRESS_ID:
                self.progress.handle_ytdlp_event(event)

        try:
            YTDLP.download(self.url, self.ydl_opts, handle_audio_progress)
            audio_file = _find_cached_media(self.url, 'audio')
            if not audio_file:
                raise RuntimeError('YT-DLP did not produce a complete audio file')
            cache_audio_progress.ready(os.path.getsize(audio_file))
        except Exception as error:
            cache_audio_progress.error(error)
            raise

    def _download_with_progress(self):
        callback = self.progress.handle_ytdlp_event if self.progress else None
        YTDLP.download(self.url, self.ydl_opts, callback)


    def video(self):
        if self.meta.get('is_live'): raise NotImplementedError('Livestream transcoding is not supported')
        mark_watched(self.url)

        height_param = "" if self.media_type.startswith('video-best') else f'[height<={self.res}]'
        if self.timestamps:
            vid = (
                get_ready_cached_video(self.url, self.cache_quality) if self.cache_quality else None
            ) or check_res_at_least(self.url, self.res)
            if vid:
                if self.progress: self.progress.encoding()
                FFMPEG(self.url, ['-i', vid, "-ss", f'{self.start_time}', "-to", f'{self.end_time}', '-vf', f'scale=-2:{self.res}', os.path.join(self.data_dir, self.media_type + '.mp4')])
            else:
                self.ydl_opts.update({"format": f"bestvideo{height_param}+bestaudio/best", "outtmpl": os.path.join(self.data_dir, f'{self.media_type}.%(ext)s')})
                self._download_with_progress()
        else:
            if vid := check_res_at_least(self.url, self.res):
                if self.progress: self.progress.encoding()
                FFMPEG(self.url, ['-i', vid, '-vf', f'scale=-2:{self.res}', os.path.join(self.data_dir, self.media_type + '.mp4')])
            else:
                success = False
                temp_video = None
                try:
                    self.ydl_opts.update({"format": f"bestvideo{height_param}/best", "outtmpl": os.path.join(self.data_dir, f'temp-{self.media_type}.%(ext)s')})
                    self._download_with_progress()
                    audio_file = check_media(self.url, 'audio') or MediaDownloader(self.url, 'audio').run()
                    temp_video = check_media(self.url, f'temp-{self.media_type}')
                    if not audio_file or not temp_video:
                        raise RuntimeError('YT-DLP did not produce complete audio and video files')
                    output_name = os.path.splitext(os.path.basename(temp_video).removeprefix('temp-'))[0] + '.mp4'
                    output_file = os.path.join(os.path.dirname(temp_video), output_name)
                    if self.progress: self.progress.encoding()
                    success = FFMPEG(self.url, [
                        '-i', audio_file,
                        '-i', temp_video,
                        '-map', '1:v:0',
                        '-map', '0:a:0',
                        '-c:v', 'copy',
                        '-c:a', 'aac',
                        '-b:a', '192k',
                        '-movflags', '+faststart',
                        output_file,
                    ]).success
                except Exception as e:
                    pprint_exc(e)
                finally:
                    if temp_video: os.remove(temp_video)
                if not success:
                    print(f'Falling back to standard video download due to FFMPEG error')
                    self.ydl_opts.update({"format": f"bestvideo{height_param}+bestaudio/best", "outtmpl": os.path.join(self.data_dir, f'{self.media_type}.%(ext)s')})
                    self._download_with_progress()


    def hls(self):
        if self.meta.get('is_live'): raise NotImplementedError('Livestream transcoding is not supported')
        mark_watched(self.url)

        res_str = 'audio' if 'audio' in self.media_type else str(self.res)
        hls_url_dir = os.path.join(gen_pathname(self.url), f"hls_segment-{res_str}")
        hls_output_dir = os.path.join(data_path, hls_url_dir)
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
        duration = get_media_duration(self.url, self.meta, ffmpeg_command[1])
        hls_url_dir = os.path.join(gen_pathname(self.url), f"hls_segment-{res_str}")
        seg_path = f"/hls_segment?url={quote_plus(self.url)}&quality={res_str}&seg="

        with open(m3u8_path, "w") as f:
            f.write(f"#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:{hls_segment_duration}\n#EXT-X-MEDIA-SEQUENCE:0\n#EXT-X-PLAYLIST-TYPE:VOD\n")
            while seg_time < duration:
                time_to_add = min(hls_segment_duration, duration - seg_time)
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
        mark_watched(self.url)
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
        if self.meta["duration"] > generate_sprite_below: raise ValueError(f"Video too long to generate sprite! ({self.meta['duration']}s)")
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



def check_alerts():
    alerts = []
    if os.environ.get('SUPRESS_WARNINGS'): return alerts
    for env_var in deprecated_env:
        if os.environ.get(env_var) is not None:
            alerts.append(f'You are using a deprecated environment variable "{env_var}" which no longer works.')
    if alerts:
        alerts.append('You can disable alerts by setting "SUPRESS_WARNINGS" environment variable to true.')
    return alerts


def download_media_file(url: str, path_without_ext: str, ext: str|None = None):
    """Download raw file with requests.get with selected filename"""
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


def stream_media_file(url: str, src: str, headers: str|None = None, cookies: str|None = None):
    """Stream raw file with requests.get"""
    try:
        headers_dict = json.loads(headers) if headers else {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        if client_range := request.headers.get('Range'):
            headers_dict['Range'] = client_range
        response = requests.get(src, stream=True, headers=headers_dict, cookies=load_http_cookies(cookies), proxies=proxies)
        response.raise_for_status()
        mime_type = response.headers.get('Content-Type', 'application/octet-stream')

        response_url = getattr(response, 'url', None) or src
        is_hls_playlist = (
            'mpegurl' in mime_type.lower()
            or urlparse(response_url).path.lower().endswith('.m3u8')
        )
        if is_hls_playlist:
            lines = []
            src_regex = re.compile(r'(URI=["\'])([^"\']*)(["\'])')
            playlist_base_url = response_url

            def proxy_playlist_url(resource_url):
                query = urlencode({
                    'src': urljoin(playlist_base_url, resource_url),
                    'headers': headers or '',
                    'cookies': cookies or '',
                    'url': url or '',
                })
                return f'/external?{query}'

            def replace_src(match):
                prefix, orig_src, suffix = match.groups()
                return f'{prefix}{proxy_playlist_url(orig_src)}{suffix}'
            raw_lines = response.content.decode('utf-8', errors='ignore').splitlines()
            skipline = False
            for idx, line in enumerate(raw_lines):
                line_str = line.strip()
                if not line_str:
                    lines.append(line)
                    continue
                if skipline:
                    skipline = False
                    continue
                if line_str.startswith('#EXTINF:0.0') and idx > (len(raw_lines) - 6):
                    print(f'Removing last short segment: {line_str}')
                    skipline = True
                    continue

                if line_str.startswith('#'):
                    lines.append(src_regex.sub(replace_src, line))
                else:
                    lines.append(proxy_playlist_url(line_str))

            resp = Response('\n'.join(lines), status=response.status_code, mimetype=mime_type)
            return resp

        def generate():
            for chunk in response.iter_content(chunk_size=8192):
                yield chunk

        resp = Response(generate(), status=response.status_code, mimetype=mime_type)

        for header in ('Content-Length', 'Content-Range'):
            if header in response.headers:
                resp.headers[header] = response.headers[header]
        resp.headers['Accept-Ranges'] = 'bytes'
        return resp
    except requests.exceptions.RequestException as e:
        print(f"Error streaming media file: {e}")
        if url: get_meta(url, 0)
        return jsonify({"error": f"Failed to stream media: {e}"}), 500



def send_file_partial(path, download_name: str | None = None):
    """Serve local media with Flask's conditional byte-range support."""
    response = send_file(path, download_name=download_name, conditional=True)
    response.headers['Accept-Ranges'] = 'bytes'
    return response



def host_file(url: str, media_type='video', download_name: str | None = None, progress: DownloadProgress | None = None):
    if not url: return jsonify({"error": "URL parameter is required"}), 400
    file = MediaDownloader(url, media_type, progress).run()
    if file:
        if progress: progress.ready(os.path.getsize(file))
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

    avail_procs = max_processes - len(Processes.get().keys())
    if not check_media(url, 'meta'):
        Thread(target=get_meta, args=[url]).start()
        avail_procs -= 1
    if not check_media(url, 'thumb'):
        Thread(target=MediaDownloader(url, 'thumb').run).start()
    if not disable_transcoding and not check_media(url, 'hls-audio') and avail_procs > 1:
        Thread(target=MediaDownloader(url, 'hls-audio').run).start()
        avail_procs -= 1
    if playlist and not check_media(url, 'playlist'):
        with open(os.path.join(get_data_dir(url), 'playlist.json'), 'w') as f:
            json.dump(playlist, f)
    if avail_procs <= 1: print('Warning: video may be loading slower than usual - consider increasing MAX_PROCESSES if that\'s an issue')


def mark_watched(url):
    if check_media(url, 'watched'): return
    if cookies := check_media(url, 'cookies') or get_global_cookies_file():
        mark_watched = lambda: YTDLP.get_info(url, ydl_global_opts | {'mark_watched': True, 'cookiefile': cookies})
        Thread(target=mark_watched).start()
        open(os.path.join(get_data_dir(url), 'watched'), 'w').close()


def get_media_duration(url, meta, media):
    try:
        if d := meta.get("duration"): return d
    except:
        pass
    ffmpeg_command = ['-i', media, '-hide_banner', '-f', 'null', '-stats']
    ff = FFMPEG(url)
    try: ff.run(ffmpeg_command)
    except Exception: pass
    info = ff.stdout
    for line in info.splitlines():
        if line.strip().startswith('Duration:'):
            duration = line.split('Duration:')[-1].split(', start:')[0].strip()
            h, m, s = duration.split(":")
            return int(h)*3600 + int(m)*60 + float(s)
    raise RuntimeError('Media duration impossible to gather - report this bug')


def get_media_res(url, meta, media):
    try:
        if meta.get("width") and meta.get("height"): return int(meta.get("width")), int(meta.get("height"))
    except: pass
    ffmpeg_command = ['-i', media, '-hide_banner', '-f', 'null', '-stats']
    ff = FFMPEG(url)
    try: ff.run(ffmpeg_command)
    except Exception: pass
    info = ff.stdout
    for line in info.splitlines():
        if line.strip().startswith('Stream'):
            for r in line.strip().split(' '):
                try:
                    w, h = r.split('x')
                    w = int(w.strip(','))
                    h = int(h.strip(','))
                    if w > 0 and h > 0: return w, h
                except:
                    pass
    raise RuntimeError('Media resolution impossible to gather - report this bug')


def pprint_exc(e, code = 500):
    error = (re.sub(r'[^\x20-\x7e]',r'', re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", str(e))))
    traceback.print_exception(e)
    return error, code


def gen_pathname(url: str):
    return sha1(url.encode()).hexdigest()


def get_data_dir(url):
    data_dir = os.path.join(data_path, gen_pathname(url))
    return data_dir


def probe_media_streams(path: str):
    ffprobe = shutil.which('ffprobe')
    if not ffprobe and ffmpeg:
        candidate = os.path.join(os.path.dirname(ffmpeg), 'ffprobe')
        if os.path.exists(candidate):
            ffprobe = candidate
    if not ffprobe:
        print(f'FFprobe unavailable; cannot inspect {path}')
        return None

    try:
        result = subprocess.run([
            ffprobe,
            '-v', 'error',
            '-show_entries', 'stream=codec_type,codec_name',
            '-of', 'json',
            path,
        ], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            print(f'FFprobe could not inspect {path}: {result.stderr.strip()}')
            return None

        return json.loads(result.stdout).get('streams') or []
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f'Could not inspect media {path}: {error}')
        return None


def _has_compatible_video_streams(streams):
    if streams is None:
        return False
    return (
        any(stream.get('codec_type') == 'video' for stream in streams)
        and any(stream.get('codec_type') == 'audio' for stream in streams)
        and not any(
            stream.get('codec_type') == 'audio'
            and stream.get('codec_name') in {'mp2', 'mp3'}
            for stream in streams
        )
    )


def is_compatible_cached_media(path: str, media_type: str):
    """Reject cached MP4 downloads whose audio codec is not broadly compatible."""
    if not media_type.startswith('video') or os.path.splitext(path)[1].lower() != '.mp4':
        return True

    streams = probe_media_streams(path)
    return streams is None or _has_compatible_video_streams(streams)


def get_ready_cached_video(url: str, quality: str, validate=True):
    """Return a complete local MP4 with video and audio, without waiting on an active cache job."""
    if not quality or quality == 'audio':
        return None

    media_type = f'video-{quality}'
    if CacheLockStore(url, media_type).media_lock_exists():
        return None

    path = check_media(url, media_type)
    if not path or os.path.splitext(path)[1].lower() != '.mp4':
        return None
    if not validate:
        return path

    if not _has_compatible_video_streams(probe_media_streams(path)):
        return None
    return path


CACHE_PROGRESS_PREFIX = 'cache-'
CACHE_AUDIO_PROGRESS_ID = f'{CACHE_PROGRESS_PREFIX}audio'
CACHE_START_MARKER_MAX_AGE = 30


def normalize_cache_quality(quality):
    quality = str(quality or '')
    if quality == 'best' or re.fullmatch(r'\d{1,4}', quality):
        return quality
    return None


def cache_progress_id(quality):
    quality = normalize_cache_quality(quality)
    return f'{CACHE_PROGRESS_PREFIX}{quality}' if quality else None


def read_video_cache_progress(url, quality):
    """Return aggregate video + audio cache progress for a validated MP4."""
    progress_id = cache_progress_id(quality)
    if not progress_id:
        return None

    progress = DownloadProgress(url, progress_id)
    video_state = DownloadProgress.read(url, progress_id) or DownloadProgress.initial_state()
    ready_video = get_ready_cached_video(url, quality)
    if ready_video:
        file_size = os.path.getsize(ready_video)
        if video_state.get('status') != 'ready' or video_state.get('total_bytes') != file_size:
            progress.ready(file_size)
            video_state = progress.state
        return video_state

    if video_state.get('status') == 'ready':
        video_state = DownloadProgress.initial_state()

    # These states describe the cache job as a whole and must take precedence
    # over its individual download components.
    if video_state.get('status') in {'encoding', 'error'}:
        return video_state

    audio_progress = DownloadProgress(url, CACHE_AUDIO_PROGRESS_ID)
    audio_state = DownloadProgress.read(url, CACHE_AUDIO_PROGRESS_ID) or DownloadProgress.initial_state()
    audio_file = _find_cached_media(url, 'audio')
    if audio_file:
        audio_size = os.path.getsize(audio_file)
        if audio_state.get('status') != 'ready' or audio_state.get('total_bytes') != audio_size:
            audio_progress.ready(audio_size)
            audio_state = audio_progress.state
    elif audio_state.get('status') == 'ready':
        audio_progress.start()
        audio_state = audio_progress.state

    component_states = (video_state, audio_state)
    downloaded = sum(
        DownloadProgress.number(state.get('downloaded_bytes'))
        for state in component_states
    )
    total = sum(
        DownloadProgress.number(state.get('total_bytes'))
        for state in component_states
    )
    speed = sum(
        DownloadProgress.number(state.get('speed'))
        for state in component_states
        if state.get('status') == 'downloading'
    )

    # Until the final MP4 exists, reserve 100% for the transition to the actual
    # FFmpeg merge. This also avoids showing 100% while the audio size is not yet
    # known or while both downloaded inputs are waiting to be merged.
    percent = min(99, downloaded / total * 100) if total else 0
    status = 'downloading' if any(
        state.get('status') in {'downloading', 'ready'}
        for state in component_states
    ) else 'preparing'

    return {
        'status': status,
        'percent': percent,
        'downloaded_bytes': downloaded,
        'total_bytes': total,
        'speed': speed,
        'timestamp': max(
            DownloadProgress.number(video_state.get('timestamp')),
            DownloadProgress.number(audio_state.get('timestamp')),
        ),
    }


def _cache_video_worker(url, quality):
    media_type = f'video-{quality}'
    progress = DownloadProgress(url, cache_progress_id(quality))
    lock_store = CacheLockStore(url, media_type)
    try:
        cached_video = MediaDownloader(url, media_type, progress).run()
        ready_video = get_ready_cached_video(url, quality)
        if not cached_video or not ready_video:
            raise RuntimeError(f'Cache did not produce a ready MP4 for {media_type}')
        progress.ready(os.path.getsize(ready_video))
    except Exception as error:
        pprint_exc(error)
        progress.error(error)
    finally:
        lock_store.release_job_lock()


def ensure_video_cache(url, quality):
    """Start one persistent background cache job and return its current state."""
    quality = normalize_cache_quality(quality)
    if not url or not quality:
        return None

    if ready_video := get_ready_cached_video(url, quality):
        progress = DownloadProgress(url, cache_progress_id(quality))
        progress.ready(os.path.getsize(ready_video))
        return progress.state

    media_type = f'video-{quality}'
    lock_store = CacheLockStore(url, media_type)
    lock_store.remove_stale_job_lock(CACHE_START_MARKER_MAX_AGE)

    if lock_store.any_lock_exists() or not lock_store.try_acquire_job_lock():
        return read_video_cache_progress(url, quality)

    progress = DownloadProgress(url, cache_progress_id(quality))
    progress.start()
    Thread(target=_cache_video_worker, args=(url, quality), daemon=True).start()
    return progress.state


def start_video_cache_if_new(url, quality):
    """Start a cache job only when this URL and quality have no prior cache state."""
    quality = normalize_cache_quality(quality)
    if not url or not quality:
        return None

    progress_id = cache_progress_id(quality)
    media_type = f'video-{quality}'
    if (
        DownloadProgress.read(url, progress_id) is not None
        or CacheLockStore(url, media_type).any_lock_exists()
        or get_ready_cached_video(url, quality)
    ):
        return read_video_cache_progress(url, quality)

    return ensure_video_cache(url, quality)


def get_global_cookies_file(force = False):
    if cookies_only_on_failure and not force: return None
    if os.path.exists('cookies.txt'): return 'cookies.txt'
    return None


def keepalive(data_dir):
    with open(os.path.join(data_dir, 'keepalive'), 'w') as f:
        f.write(str(int(time.time())))


def _find_cached_media(url: str, media_type: str):
    data_dir = get_data_dir(url)
    try:
        for i in os.listdir(data_dir):
            if '.part' in i: continue
            if i.endswith('.ytdl'): continue
            if i.endswith('.temp'): continue
            if i.count('_') != media_type.count('_'): continue
            if i.startswith(media_type):
                return os.path.join(data_dir, i)
    except:
        return None
    return None


def check_media(url: str, media_type: str):
    print(f'Checking media for {url=} and {media_type=}')
    path = _find_cached_media(url, media_type)
    if path:
        print(f'Serving {path}')
        keepalive(get_data_dir(url))
        print(f'Media for {url=} and {media_type=} found')
    return path


def get_meta(url: str, max_meta_age = None):
    with FileCachingLock(url, 'meta') as cache:
        print(cache)
        if cache:
            try:
                with open(cache, 'r') as f:
                    meta = json.load(f)
                max_meta_age = max_meta_age or (60 if meta.get('is_live') else 600)
                if time.time() - meta.get('timestamp') > max_meta_age:
                    print('Checking metadata validity...')
                    srcs = choose_sources_for_res(get_video_sources(url, meta), get_good_quality(get_video_formats(url, meta)))
                    src = srcs[0] or srcs[1]
                    resp = stream_media_file(url, src[0], src[1], src[2])
                    if isinstance(resp, Response):
                        if resp.status_code > 399: raise ConnectionError(resp.response)

                        mime_type = resp.headers.get('Content-Type') or ''
                        if 'mpegurl' in mime_type.lower():

                            raw_lines = resp.data.decode('utf-8', errors='ignore').splitlines()
                            for line in raw_lines:
                                line_str = line.strip()
                                if not line_str or line_str.startswith('#'): continue
                                resp = stream_media_file(None, urljoin(url, line_str), src[1], src[2])
                                if not isinstance(resp, Response) or resp.status_code > 399: raise ConnectionError('Can not send a HLS request')
                                break

                    else: raise ConnectionError('Can not send a request')
                    meta['timestamp'] = int(time.time())
                    with open(cache, 'w') as f:
                        json.dump(meta, f)
                    print('Metadata still valid')
                return meta
            except Exception as e:
                pprint_exc(e)
                print('Meta file invalid - Regenerating...')
                data_dir = get_data_dir(url)
                for file in os.listdir(data_dir):
                    if os.path.isdir(os.path.join(data_dir, file)): continue
                    try: os.remove(os.path.join(data_dir, file))
                    except: pass
        print(f'downloading meta for {url}')
        ydl_opts = {'skip_download': True}
        ydl_opts.update(ydl_global_opts)
        if cookies := check_media(url, 'cookies') or get_global_cookies_file(): ydl_opts["cookiefile"] = cookies
        info = YTDLP.get_info(url, ydl_opts)
        if info.get('entries'): info = info['entries'][0]

        if not info.get('duration') or not info.get('width') or not info.get('height'):
            try:
                print('Fetching additional info for meta')
                srcs = choose_sources_for_res(get_video_sources(url, info), get_good_quality(get_video_formats(url, info)))
                src = srcs[0] or srcs[1]
                duration = get_media_duration(url, None, src[0])
                w, h = get_media_res(url, None, src[0])
                info['duration'] = duration
                info['width'] = w
                info['height'] = h
            except Exception as e:
                pprint_exc(e)

        info['original_url'] = url
        info['timestamp'] = int(time.time())
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
        if int(f.get('height') or 0) > max_quality: continue
        if (f.get('vcodec') or 'none').lower() != 'none' or ((f.get('video_ext') or 'none').lower() != 'none'):
            video_name = f"{(f.get('height') or meta.get('height') or '1')}"
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


def generate_hls(url, audio_source, video_source):

    get_url = lambda s: f'/external?src={quote_plus(s[0])}&headers={quote_plus(s[1])}&cookies={quote_plus(s[2])}&url={quote_plus(url)}'

    audio_url = get_url(audio_source) if audio_source and audio_source != video_source else None
    video_url = get_url(video_source) if video_source else None
    audio_grp = ',AUDIO="audio_grp"'

    return '\n'.join([
        '#EXTM3U',
        '#EXT-X-VERSION:3',
        f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio_grp",NAME="English",DEFAULT=YES,AUTOSELECT=YES,URI="{audio_url}"' if audio_url and video_url else "",
        f'#EXT-X-STREAM-INF:BANDWIDTH=1500000{audio_grp if audio_url and video_url else ""}',
        f'{video_url}' if video_url else f'{audio_url}'
    ])


def generate_dash(url, audio_source, video_source, duration):
    def get_mp4_dash_ranges(source):
        headers_dict = json.loads(source[1]) | {"Range": "bytes=0-60000"}
        response = requests.get(source[0], headers=headers_dict, cookies=load_http_cookies(source[2]), proxies=proxies)
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
       f'            <BaseURL><![CDATA[/external?src={quote_plus(src[0])}&headers={quote_plus(src[1])}&cookies={quote_plus(src[2])}&url={quote_plus(url)}]]></BaseURL>',
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
    try:
        url = url or meta.get('original_url')
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
                    content = generate_hls(url, a, v)
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
                    content = generate_dash(url, a, v, get_media_duration(url, meta, a[0] if a else v[0]))
                    with open(os.path.join(get_data_dir(url), f'direct-{res or "audio"}.mpd'), 'w') as f:
                        f.write(content)
                except Exception as e:
                    pprint_exc(e)
            return 'application/dash+xml'
    except Exception as e:
        pprint_exc(e)
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
                response = requests.get(img_url, proxies=proxies)
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
    info['cache_quality'] = get_good_quality(info['formats'])
    info['default_quality'] = 'audio' if 'Music' in (meta.get('categories') or []) and audio_visualizer else info['cache_quality']
    info['autoplay'] = autoplay
    info['min_live_buffer'] = min_live_buffer
    info['always_transcode'] = always_transcode
    info['disable_transcoding'] = disable_transcoding
    info['hls_duration'] = hls_duration
    info['hls_audio_duration'] = hls_audio_duration
    info['playlist_support'] = playlist_support
    info['auto_bg_playback'] = auto_bg_playback
    info['audio_visualizer'] = audio_visualizer
    info['autoskip_sb_segments'] = autoskip_sb_segments
    info['chapters'] = generate_chapters(meta)
    auto_sprite = get_sprite(info['url'], meta, True)
    info['generate_sprite_below'] = max_video_duration if (auto_sprite and generate_sprite_below > 0) else generate_sprite_below
    info['sprite'] = auto_sprite or [160, 90, 10, 10]
    if meta.get('is_live'):
        info['subtitles'] = []
        info['duration'] = '0'
    info['alerts'] = check_alerts()
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
    url = req.args.get('v') or req.args.get('url') or None
    if url is None or len(url) < 3: return None
    return normalize_url(url)


def append_query_to_url(url, query):
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    query_params['q'] = query
    new_query_string = urlencode(query_params, doseq=True)
    return urlunparse(parsed_url._replace(query=new_query_string))
