import os
import json
import shutil
import signal
import sys
from flask import Flask, render_template, request, jsonify, Response
from io import BytesIO
from starlette.middleware.wsgi import WSGIMiddleware

from main import *
from addons import *
from external import External
import library_db
import log_capture

log_capture.init(os.path.join(data_path, 'app.log'))
library_db.init_db()


app = Flask(__name__)
wsgi = WSGIMiddleware(app)

def signal_handler(signum, frame):
    print(f"Signal {signum} received. Shutting down...")
    Processes.rm_all()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def _render_home():
    print('Started serving home/library')
    show_hidden = request.args.get('show_hidden') in ('1', 'true', 'yes')
    ydl_version = External.get_ytdlp_version()
    js_runtime_version = External.get_js_runtime_version(js_runtime)
    ffmpeg_version = External.get_ffmpeg_version(ffmpeg)
    entries = library_db.list_videos(include_hidden=show_hidden)
    grouped = {}
    for e in entries:
        grouped.setdefault(e.get('source_site') or 'unknown', []).append(e)
    grouped = dict(sorted(grouped.items(), key=lambda kv: kv[0]))
    all_tags = library_db.list_tags(include_hidden=show_hidden)
    all_categories = library_db.list_categories(include_hidden=show_hidden)
    all_sites = library_db.list_sites(include_hidden=show_hidden)
    hidden_sites = library_db.list_hidden_sites()
    print('Stopped serving home/library')
    return render_template('index.html',
        entries=entries, grouped=grouped, total=len(entries),
        all_tags=all_tags, all_categories=all_categories, all_sites=all_sites,
        hidden_sites=hidden_sites, show_hidden=show_hidden,
        ydl_version=ydl_version, app_version=app_version,
        js_runtime_version=js_runtime_version, ffmpeg_version=ffmpeg_version,
        app_title=app_title, theme_color=theme_color, amoled_bg=amoled_bg)


@app.route('/')
def index():
    return _render_home()


@app.route('/library')
def library():
    return _render_home()


@app.route('/library/rebuild', methods=['POST'])
def library_rebuild():
    try:
        count = library_db.rebuild()
    except Exception as e:
        return pprint_exc(e)
    return jsonify({"ok": True, "count": count}), 200


@app.route('/library/delete', methods=['POST'])
def library_delete():
    url = get_url(request)
    if not url: return jsonify({"error": "URL parameter is required"}), 400
    Processes.rm_all(url)
    vid_dir = get_data_dir(url)
    library_db.delete_video(url)
    if not os.path.isdir(vid_dir): return jsonify({"ok": True, "note": "not on disk"}), 200
    try:
        shutil.rmtree(vid_dir)
    except Exception as e:
        return pprint_exc(e)
    return jsonify({"ok": True}), 200


@app.route('/library/hide', methods=['POST'])
def library_hide():
    url = get_url(request)
    if not url: return jsonify({"error": "URL parameter is required"}), 400
    library_db.hide_video(url)
    return jsonify({"ok": True}), 200


@app.route('/library/unhide', methods=['POST'])
def library_unhide():
    url = get_url(request)
    if not url: return jsonify({"error": "URL parameter is required"}), 400
    library_db.unhide_video(url)
    return jsonify({"ok": True}), 200


@app.route('/library/site/hide', methods=['POST'])
def library_site_hide():
    name = request.args.get('name', '').strip().lower()
    if not name: return jsonify({"error": "name parameter is required"}), 400
    library_db.hide_site(name)
    return jsonify({"ok": True}), 200


@app.route('/library/site/unhide', methods=['POST'])
def library_site_unhide():
    name = request.args.get('name', '').strip().lower()
    if not name: return jsonify({"error": "name parameter is required"}), 400
    library_db.unhide_site(name)
    return jsonify({"ok": True}), 200


@app.route('/logs')
def logs_page():
    return render_template('logs.html', app_title=app_title, theme_color=theme_color, amoled_bg=amoled_bg, log_path=log_capture.LOG_PATH)


@app.route('/logs/tail')
def logs_tail():
    since = request.args.get('since', type=int)
    if since is None:
        data, size = log_capture.read_tail()
    else:
        data, size = log_capture.read_since(since)
    resp = Response(data, mimetype='text/plain; charset=utf-8')
    resp.headers['X-Log-Size'] = str(size)
    return resp


@app.route('/logs/clear', methods=['POST'])
def logs_clear():
    path = log_capture.LOG_PATH
    if not path: return jsonify({"error": "log capture not initialized"}), 500
    try:
        open(path, 'w').close()
    except Exception as e:
        return pprint_exc(e)
    return jsonify({"ok": True}), 200


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
    meta = None

    if check_media(url, 'meta'):
        meta = get_meta(url)
        video_width = meta.get('width') or video_width
        video_height = meta.get('height') or video_height
        video_title = meta.get('title') or app_title
    preload(url)
    if url:
        Thread(target=post_media_hooks, args=(url,), daemon=True).start()

    debug = _watch_debug(url, meta)

    print('Stopped serving watch')
    return render_template('watch.html', original_url=url, ydl_version=ydl_version, app_version=app_version, js_runtime_version=js_runtime_version, ffmpeg_version=ffmpeg_version, app_title=app_title, theme_color=theme_color, amoled_bg=amoled_bg, video_width=video_width, video_height=video_height, video_title=video_title, debug=debug)


def _format_size(n):
    if n is None: return ''
    step = 1024.0
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    i = 0
    x = float(n)
    while x >= step and i < len(units) - 1:
        x /= step
        i += 1
    return f'{x:.1f} {units[i]}' if i else f'{int(x)} {units[i]}'


def _watch_debug(url, meta):
    dir_hash = gen_pathname(url) if url else None
    data_dir = get_data_dir(url) if url else None
    files = []
    if data_dir and os.path.isdir(data_dir):
        for name in sorted(os.listdir(data_dir)):
            p = os.path.join(data_dir, name)
            try:
                if os.path.isdir(p):
                    files.append({'name': name + '/', 'size': '', 'is_dir': True})
                else:
                    files.append({'name': name, 'size': _format_size(os.path.getsize(p)), 'is_dir': False})
            except OSError:
                pass
    highlights = {}
    if meta:
        for k in ('extractor', 'extractor_key', 'title', 'uploader', 'uploader_id', 'channel', 'upload_date',
                  'duration', 'width', 'height', 'fps', 'is_live', 'filesize_approx', 'ext', 'protocol', 'language'):
            v = meta.get(k)
            if v is not None and v != '':
                highlights[k] = v
    return {
        'url': url,
        'dir_hash': dir_hash,
        'data_dir': data_dir,
        'files': files,
        'meta_highlights': highlights,
        'has_meta': meta is not None,
    }


@app.route('/debug/meta')
def debug_meta():
    url = get_url(request)
    if not url: return jsonify({"error": "URL parameter is required"}), 400
    if not check_media(url, 'meta'): return jsonify({"error": "No meta cached for that URL"}), 404
    meta = get_meta(url)
    pretty = request.args.get('pretty', '1') != '0'
    return Response(
        json.dumps(meta, indent=2 if pretty else None, default=str),
        mimetype='application/json'
    )


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
