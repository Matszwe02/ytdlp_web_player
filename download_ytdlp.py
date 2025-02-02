import os
import platform
import requests

YT_DLP = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux"
YT_DLP_ARM = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux_armv7l"
YT_DLP_ARM64 = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux_aarch64"
YT_DLP_WIN = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"

def download():
    if os.path.exists('yt-dlp'):
        os.remove('yt-dlp')
    if os.path.exists('yt-dlp.exe'):
        os.remove('yt-dlp.exe')
        
    print('Downloading yt-dlp...')
    if platform.system() == 'Windows':
        url = YT_DLP_WIN
    else:
        if platform.machine() == 'armv7l':
            url = YT_DLP_ARM
        elif platform.machine() == 'aarch64' or platform.machine() == 'arm64':
            url = YT_DLP_ARM64
        else:
            url = YT_DLP
    
    response = requests.get(url)
    with open('yt-dlp', 'wb') as f:
        f.write(response.content)
    print('yt-dlp downloaded successfully')

    if platform.system() == 'Windows':
        pass
    else:
        if not os.access('yt-dlp', os.X_OK):
            print('Making yt-dlp executable...')
            os.chmod('yt-dlp', 0o755)
            print('yt-dlp is now executable')
        else:
            print('yt-dlp is already executable')


