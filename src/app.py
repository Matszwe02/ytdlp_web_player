import os
import signal
import sys
import json
import time
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from io import BytesIO
from starlette.middleware.wsgi import WSGIMiddleware

from main import *
from addons import *
from external import External


app = Flask(__name__)
wsgi = WSGIMiddleware(app)

def signal_handler(signum, frame):
    print(f"Signal {signum} received. Shutting down...")
    Processes.rm_all()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def _cache_pending_response(status='preparing'):
    return Response(status=202, headers={
        'X-Cache-Status': status,
        'Retry-After': '1',
        'Cache-Control': 'no-store',
    })


@app.route('/')
def index():
    print('Started serving root')
    ydl_version = External.get_ytdlp_version()
    js_runtime_version = External.get_js_runtime_version(js_runtime)
    ffmpeg_version = External.get_ffmpeg_version(ffmpeg)
    print('Stopped serving root')
    return render_template('index.html', ydl_version=ydl_version, app_version=app_version, js_runtime_version=js_runtime_version, ffmpeg_version=ffmpeg_version, app_title=app_title, theme_color=theme_color, amoled_bg=amoled_bg)


@app.route('/watch')
def watch():
    print('Started serving watch')
    ydl_version = External.get_ytdlp_version()
    js_runtime_version = External.get_js_runtime_version(js_runtime)
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
    return render_template('watch.html', original_url=url, ydl_version=ydl_version, app_version=app_version, js_runtime_version=js_runtime_version, ffmpeg_version=ffmpeg_version, app_title=app_title, theme_color=theme_color, amoled_bg=amoled_bg, video_width=video_width, video_height=video_height, video_title=video_title)


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
        pprint_exc(e)
        thumb = BytesIO()
        Image.new('RGB', (10, 10), color = 'black').save(thumb, format='PNG')
        thumb.seek(0)
        return Response(thumb, mimetype='image/png')


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
        res = request.args.get('quality') or ''
        start_time = request.args.get('start', 0, type=float)
        end_time = request.args.get('end', 0, type=float)
        is_trimmed = start_time > 0 or end_time > 0

        media_type = 'audio' if res == 'audio' else f'video-{res}'.removesuffix('-')

        if is_trimmed:
            media_type += f'_{start_time:.1f}-{end_time:.1f}'

        url = get_url(request)
        if not url: return jsonify({"error": "URL parameter is required"}), 400

        cache_quality = normalize_cache_quality(res) if res != 'audio' else None

        if cache_quality is not None:
            cache_state = ensure_video_cache(url, cache_quality) or DownloadProgress.initial_state()
            if cache_state.get('status') != 'ready':
                return _cache_pending_response(cache_state.get('status') or 'preparing')

            # ensure_video_cache only reports ready after validating the MP4.
            # Avoid running FFprobe again for the immediately following response.
            cached_video = get_ready_cached_video(url, cache_quality, validate=False)
            if not cached_video:
                return _cache_pending_response()

            if not is_trimmed:
                try:
                    video_title = get_meta(url, float('inf')).get('title')
                except Exception as error:
                    pprint_exc(error)
                    video_title = None
                download_name = f'{video_title}-{res}.mp4' if video_title else None
                return send_file_partial(cached_video, download_name=download_name)

        video_title = get_meta(url).get('title')
        return host_file(url, media_type, download_name=video_title)

    except Exception as e:
        return pprint_exc(e)


@app.route('/cache-progress-stream')
def video_cache_progress_stream():
    url = get_url(request)
    quality = normalize_cache_quality(request.args.get('quality'))
    if not url: return jsonify({"error": "URL parameter is required"}), 400
    if not quality: return jsonify({"error": "A numeric or best video quality is required"}), 400

    def generate_events():
        start_video_cache_if_new(url, quality)
        previous_event = None
        next_keepalive = time.monotonic() + 15
        yield 'retry: 3000\n\n'

        while True:
            state = read_video_cache_progress(url, quality)
            event = json.dumps(state, separators=(',', ':'))
            if event != previous_event:
                yield f'data: {event}\n\n'
                previous_event = event
                next_keepalive = time.monotonic() + 15
            elif time.monotonic() >= next_keepalive:
                yield ': keep-alive\n\n'
                next_keepalive = time.monotonic() + 15

            if state.get('status') == 'ready':
                return
            time.sleep(DownloadProgress.update_interval)

    response = Response(stream_with_context(generate_events()), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache, no-transform'
    response.headers['X-Accel-Buffering'] = 'no'
    return response


@app.route('/low')
def download_low_quality():
    try:
        return host_file(get_url(request), 'low')
    except Exception as e:
        return pprint_exc(e)


@app.route('/direct')
def resp_direct():
    try:
        res = request.args.get('quality') or ''
        media_type = f'direct-{res}'.removesuffix('-')
        url = get_url(request)
        playback_source = request.args.get('playback') or 'auto'

        cached_video = None if playback_source == 'stream' else get_ready_cached_video(
            url, res, validate=playback_source != 'local'
        )
        if cached_video:
            response = send_file_partial(cached_video)
            response.headers['X-Playback-Source'] = 'local'
            return response

        # The browser uses this HEAD request only to choose between local and
        # streamed playback. Do not open an upstream media connection here.
        if request.method == 'HEAD':
            response = Response(status=200)
            response.headers['X-Playback-Source'] = 'stream'
            response.headers['Cache-Control'] = 'no-store'
            return response

        media = check_media(url, media_type) or MediaDownloader(url, media_type).run()
        if media and media.endswith('.url'):
            with open(media, 'r') as f:
                src = f.readline().rstrip('\n')
                headers = f.readline().rstrip('\n')
                cookies = f.read().rstrip('\n')
            response = stream_media_file(url, src, headers, cookies)
        elif media:
            response = send_file_partial(media)
        else:
            response = jsonify({"error": f"Cannot gather {media_type}"}), 404

        if isinstance(response, Response):
            response.headers['X-Playback-Source'] = 'stream'
        return response
    except Exception as e:
        return pprint_exc(e)


@app.route('/external')
def serve_external():
    src = request.args.get('src')
    url = get_url(request)
    return stream_media_file(url, src, request.args.get('headers'), request.args.get('cookies'))


@app.route('/subtitle')
def serve_subtitle():
    return host_file(get_url(request), f'sub-{request.args.get("lang")}')


@app.route('/info')
def serve_info():
    try:
        url = get_url(request)
        if not url: return jsonify({"error": "URL parameter is required"}), 400
        return get_video_info(get_meta(url))
    except Exception as e:
        return pprint_exc(e)


@app.route('/manifest.json')
def serve_manifest():
    manifest = render_template('manifest.json', app_title=app_title, theme_color=theme_color, amoled_bg=amoled_bg)
    return Response(manifest.encode('utf-8'), mimetype='application/manifest+json')


@app.route('/playlist')
def serve_playlist():
    try:
        return host_file(get_url(request), 'playlist')
    except Exception as e:
        return pprint_exc(e)


@app.route('/favicon.svg')
def serve_favicon():
    with open(os.path.join(app.static_folder, 'favicon.svg'), 'r') as f:
        favicon = f.read()
    favicon = favicon.replace('#ff7300', theme_color)
    return Response(favicon, mimetype='image/svg+xml')


@app.route('/favicon<int:size>.png')
def serve_favicon_png(size=512):

    from PIL import Image

    img = Image.open(os.path.join(app.static_folder, 'favicon-template.png')).convert('RGBA')
    color = tuple(int(theme_color[i:i+2], 16) / 255 for i in (1, 3, 5))

    data = img.getdata()
    new_data = []
    for item in data:
        new_data.append((int(item[0] * color[0]), int(item[1] * color[1]), int(item[2] * color[2]), item[3]))

    img.putdata(new_data)
    img = img.resize((size, size), Image.Resampling.BICUBIC)

    favicon_png = BytesIO()
    img.save(favicon_png, format='PNG')
    favicon_png.seek(0)
    return Response(favicon_png, mimetype='image/png')


@app.route('/sw.js')
def serve_sw():
    with open(os.path.join(app.static_folder, 'sw.js'), 'r') as f:
        sw = f.read()
    return Response(sw, mimetype='text/javascript')


@app.route('/extension.js')
def serve_extension():
    if os.path.exists(os.path.join(app.static_folder, 'extension.js')):
        with open(os.path.join(app.static_folder, 'extension.js'), 'r') as f:
            extension = f.read()
    elif os.path.exists(os.path.join('../extension', 'extension.js')):
        with open(os.path.join('../extension', 'extension.js'), 'r') as f:
            extension = f.read()
    else:
        return stream_media_file('https://raw.githubusercontent.com/Matszwe02/ytdlp_web_player/refs/heads/main/extension/extension.js')
    request_url = request.url_root.rstrip('/')
    if p := request.headers.get('X-Forwarded-Proto'): request_url = request_url.replace('http', p, 1)

    extension = extension.replace('https://github.com/Matszwe02/ytdlp_web_player/raw/main/extension', request_url)
    extension = extension.replace('https://github.com/Matszwe02/ytdlp_web_player/raw/main/src/static', request_url)
    extension = extension.replace('1.0.0', External.get_app_version(), 1)
    extension = extension.replace('YT-DLP Web Player', app_title, 1)
    extension = extension.replace("var playerUrl = '';", f"var playerUrl = '{request_url}';", 1)

    return Response(extension, mimetype='text/javascript')


@app.route('/hls')
def download_hls():
    try:
        res = (request.args.get('quality') or '')  
        media_type = f'hls-{res}'.removesuffix('-')
        return host_file(get_url(request), media_type)
    except Exception as e:
        return pprint_exc(e)


@app.route('/hls_segment')
def hls_segment():
    url = get_url(request)
    data_dir = get_data_dir(url)
    quality = request.args.get('quality')
    seg = request.args.get('seg')
    file = os.path.join(data_dir, f'hls_segment-{quality}/segment{seg:>0{4}}.ts')

    if not os.path.exists(file):
        media_type = f'hls-{quality}'.removesuffix('-')
        host_file(get_url(request), media_type)
        return jsonify({"error": "File not found"}), 404

    return send_file_partial(file)


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
