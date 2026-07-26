import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile


ffmpeg_version = '-'
js_runtime_version = 'Node-'
app_version = '-'

class External:


    @staticmethod
    def yt_dlp():
        import yt_dlp
        try:
            import yt_dlp.version
        except:
            print('Warning: ytdlp does not support version')
        return yt_dlp


    @staticmethod
    def _pip_install(package):
        if getattr(sys, 'frozen', False): raise RuntimeError('This environment does not allow installing packages')
        python = sys.executable or 'python3'
        try:
            subprocess.run([python, '-m', 'pip', 'install', '--upgrade', package], capture_output=True, text=True, timeout=120, check=True)
        except Exception as e:
            print(f'Warning: pip install of {package} failed: {e}')


    @staticmethod
    def download_ytdlp():
        print('Downloading latest yt-dlp...')
        try:
            if getattr(sys, 'frozen', False):
                External._load_frozen_ytdlp()
            else:
                External._pip_install('yt-dlp')
            try:
                import importlib
                importlib.reload(yt_dlp)
                importlib.reload(yt_dlp.version)
                importlib.util
            except:
                import yt_dlp
                import yt_dlp.version
        except Exception as e:
            print(f'Warning: yt-dlp update failed: {e}')


    @staticmethod
    def download_ffmpeg() -> str|None:
        try:
            p = os.path.dirname(__file__)
            for f in os.listdir(p):
                if f.startswith('ffmpeg'): return os.path.abspath(os.path.join(p, f))
            if f := shutil.which("ffmpeg"): return os.path.abspath(f)
            try:
                import pyffmpeg # type: ignore
            except Exception:
                print('Installing "pyffmpeg" to project\'s environment')
                External._pip_install('pyffmpeg')
                import pyffmpeg # type: ignore
            return os.path.abspath(pyffmpeg.FFmpeg().get_ffmpeg_bin())
        except Exception:
            return None


    @staticmethod
    def download_deno() -> str|None:
        try:
            p = os.path.dirname(__file__)
            for f in os.listdir(p):
                if f.startswith('deno') or f.startswith('node'): return os.path.abspath(os.path.join(p, f))
            if f := shutil.which("deno") or shutil.which("node"): return os.path.abspath(f)
            try:
                import deno # type: ignore
            except Exception:
                print('Installing "deno" to project\'s environment')
                External._pip_install('deno')
                import deno # type: ignore
            return os.path.abspath(deno.find_deno_bin())
        except Exception:
            return None


    @staticmethod
    def get_js_runtime_version(js_runtime_path):
        global js_runtime_version
        if js_runtime_version != 'Node-': return js_runtime_version
        try:
            ver_str = subprocess.run([js_runtime_path, '--version'], capture_output=True).stdout.splitlines()[0].decode()
            js_runtime_version = ver_str.split("(")[0].split("deno")[-1].strip() or 'Node-'
            js_runtime_version = ('Deno' if 'deno' in ver_str.lower() else 'Node') + js_runtime_version
        except Exception:
            js_runtime_version = 'Node-'
        return js_runtime_version


    @staticmethod
    def get_ffmpeg_version(ffmpeg_path):
        global ffmpeg_version
        if ffmpeg_version != '-': return ffmpeg_version
        try:
            ver_str = subprocess.run([ffmpeg_path, '-version'], capture_output=True).stdout.splitlines()[0].decode()
            ffmpeg_version = ver_str.split("sion")[-1].split("Copyright")[0] or '-'
        except Exception:
            ffmpeg_version = '-'
        return ffmpeg_version


    @staticmethod
    def get_app_version():
        global app_version
        if app_version != '-': return app_version
        try:
            if os.path.exists('version.txt'):
                with open('version.txt', 'r') as f:
                    app_version = f.read()
            else:
                import version
                shutil.move('version.txt', 'version-dynamic.txt')
                with open('version-dynamic.txt', 'r') as f:
                    app_version = f.read()
        except Exception as e:
            print(e)
            return '-'
        return app_version


    @staticmethod
    def get_ytdlp_version():
        try:
            return External.yt_dlp().version.__version__ or '-'
        except:
            return '-'


    @staticmethod
    def _install_ytdlp_raw(ytdlp_dir):

        print('Installing yt-dlp from wheel...')

        with urllib.request.urlopen("https://pypi.org/pypi/yt-dlp/json", timeout=10) as r:
            data = json.load(r)
        version = data["info"]["version"]
        url = [f for f in data["releases"][version] if f["filename"].endswith(".whl")][0]["url"]

        shutil.rmtree(ytdlp_dir, ignore_errors=True)
        wheel_path = os.path.join(ytdlp_dir, '.whl')
        os.makedirs(wheel_path, exist_ok=True)

        wheel = os.path.join(wheel_path, "yt-dlp.whl")
        with urllib.request.urlopen(url, timeout=60) as r, open(wheel, "wb") as f:
            shutil.copyfileobj(r, f)
        with zipfile.ZipFile(wheel) as z:
            z.extractall(ytdlp_dir)
        print(f'Yt-dlp {version} installed!')


    @staticmethod
    def _load_frozen_ytdlp():
        ytdlp_dir = str(os.path.abspath('./yt-dlp_update'))
        External._install_ytdlp_raw(ytdlp_dir)

        sys.modules.pop("yt_dlp", None)
        sys.modules.pop("yt_dlp.version", None)

        if str(ytdlp_dir) in sys.path: sys.path.remove(ytdlp_dir)
        sys.path.insert(0, ytdlp_dir)
