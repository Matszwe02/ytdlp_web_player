import os
import signal
import sys
from flask import Flask, render_template, request, jsonify, Response
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
def resp_direct():
    try:
        res = request.args.get('quality') or ''
        media_type = f'direct-{res}'.removesuffix('-')
        url = get_url(request)
        media = check_media(url, media_type)
        if media and media.endswith('.url'):
            with open(media, 'r') as f:
                return stream_media_file(f.readline().rstrip('\n'), f.readline().rstrip('\n'), f.readline().rstrip('\n'))
        return host_file(url, media_type)
    except Exception as e:
        return pprint_exc(e)


@app.route('/external')
def serve_external():
    url = request.args.get('url')
    if not url: return jsonify({"error": "URL parameter is required"}), 400
    return stream_media_file(url, request.args.get('headers'), request.args.get('cookies'))


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
