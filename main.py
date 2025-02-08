from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from urllib.parse import unquote
import os
import uuid
from datetime import datetime, timedelta
import time
from threading import Thread
from download_ytdlp import downloader
import subprocess
import requests


app = Flask(__name__)
DOWNLOAD_PATH = './download'
os.makedirs(DOWNLOAD_PATH, exist_ok=True)
os.environ['PATH'] = os.pathsep.join([os.getcwd(), os.environ['PATH']])


def ytdlp_download():
    while True:
        time.sleep(86400) # 24 hours
        downloader()


def delete_old_files():
    while True:
        try:
            now = datetime.now()
            cutoff = now - timedelta(minutes=10)
            for filename in os.listdir(DOWNLOAD_PATH):
                file_path = os.path.join(DOWNLOAD_PATH, filename)
                if os.path.isfile(file_path):
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if file_time < cutoff:
                        os.remove(file_path)
                        print(f"Deleted old file: {file_path}")
        except: pass
        time.sleep(600)


def get_url(req):
    url = req.args.get('v') or req.args.get('url')
    if '.' not in url:
        url = 'https://youtube.com/watch?v=' + url
    return url

    


@app.route('/')
def index():
    return redirect('/watch')



@app.route('/watch')
def watch():
    try:
        version = subprocess.run(['./yt-dlp', '--version'], capture_output=True, text=True).stdout.strip()
    except:
        try:
            downloader()
            version = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True).stdout.strip()
        except:
            version = 'none'
    return render_template('watch.html', version=version)


@app.route('/search')
def search():
    url = get_url(request)

    if not url:
        return '', 404

    command = ['./yt-dlp', '-f', 'best', '--get-url', url]
    result = subprocess.run(command, capture_output=True, text=True)
    streaming_url = result.stdout.strip()
    if not streaming_url:
        return '', 404

    # Check for media availability at streaming_url
    response = requests.head(streaming_url)
    if response.status_code == 200:
        return streaming_url
    
    
    
    unique_filename = str(uuid.uuid4())
    output_path = os.path.join(DOWNLOAD_PATH, unique_filename + '.%(ext)s')
    command = ['./yt-dlp', '-o', output_path, unquote(url)]
    subprocess.run(command, check=True)
    for i in os.listdir(DOWNLOAD_PATH):
        if i.startswith(unique_filename):
            return  'download/' + i
    
    return 'Cannot gather video', 404


# display raw video
@app.route('/raw')
def raw():
    url = search()
    html_template = f'<video controls autoplay><source src="{url}" type="video/mp4"></video>'
    return html_template


@app.route('/download/<path:filename>')
def download_ytdlp(filename):
    print(filename)
    print(os.path.join('download', filename))
    print(os.path.exists(os.path.join('download', filename)))
    return send_from_directory('download', filename)


if __name__ == '__main__':
    thread = Thread(target=delete_old_files)
    downloader_thread = Thread(target=ytdlp_download)
    thread.start()
    downloader_thread.start()
    app.run()