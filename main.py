from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from urllib.parse import unquote
import os
import uuid
from datetime import datetime, timedelta
import time
from threading import Thread
import download_ytdlp
import subprocess

app = Flask(__name__)
DOWNLOAD_PATH = './download'
last_ytdlp_download = datetime.now() - timedelta(weeks=10)


def ytdlp_download():
    global last_ytdlp_download
    if (datetime.now() - last_ytdlp_download).total_seconds() > 86400: # 1 day
        download_ytdlp.download()
        last_ytdlp_download = datetime.now()


def delete_old_files():
    while True:
        now = datetime.now()
        cutoff = now - timedelta(minutes=10)
        for filename in os.listdir(DOWNLOAD_PATH):
            file_path = os.path.join(DOWNLOAD_PATH, filename)
            if os.path.isfile(file_path):
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_time < cutoff:
                    os.remove(file_path)
                    print(f"Deleted old file: {file_path}")
        time.sleep(600)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/watch')
def watch():
    try:
        version = subprocess.run(['./yt-dlp', '--version'], capture_output=True, text=True).stdout.strip()
    except:
        version = ''
    return render_template('watch.html', version=version)


@app.route('/search')
def search():
    ytdlp_download()
    yt_url = request.args.get('v')
    standard_url = request.args.get('url')
    download_url = request.args.get('download')

    if not yt_url and not standard_url and not download_url:
        return 'No video URL provided', 404

    if yt_url or standard_url:
        url = 'https://youtube.com/watch?v=' + yt_url if yt_url else unquote(standard_url)
        command = ['./yt-dlp', '-f', 'best', '--get-url', url]
        result = subprocess.run(command, capture_output=True, text=True)
        streaming_url = result.stdout.strip()
        if not streaming_url:
            return 'No streaming URL found', 404
    else:
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        unique_filename = str(uuid.uuid4())
        output_path = os.path.join(DOWNLOAD_PATH, unique_filename + '.%(ext)s')
        command = ['./yt-dlp', '-o', output_path, unquote(download_url)]
        subprocess.run(command, check=True)
        path = ''
        for i in os.listdir(DOWNLOAD_PATH):
            if i.startswith(unique_filename):
                path = i
                break
        streaming_url = 'download/' + path
    return streaming_url

# display raw video
@app.route('/raw')
def raw():
    url = search()
    html_template = f'<video controls autoplay><source src="{url}" type="video/mp4"></video>'
    return html_template


@app.route('/download/<path:filename>')
def download(filename):
    print(filename)
    print(os.path.join('download', filename))
    print(os.path.exists(os.path.join('download', filename)))
    return send_from_directory('download', filename)


if __name__ == '__main__':
    thread = Thread(target=delete_old_files, daemon=True)
    thread.start()
    app.run()