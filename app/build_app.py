import importlib
import os
import platform
import shutil
import site
import subprocess
import sys
import zipfile


os.chdir(os.path.dirname(__file__))

app_version = sys.argv[-1].replace('"', '').strip()
if not app_version.startswith('v'): app_version = 'v1.0.0'
platform_name = f'{platform.system().lower()}-{platform.machine().replace("AMD", "x").lower()}'
python = sys.executable or 'python3'
colon = ';' if os.name == 'nt' else ':'


def run_subprocess(args, cwd=None):
    print(f'Running {args}')
    try:
        subprocess.run(args, capture_output=True, text=True, timeout=300, check=True, cwd=cwd)
    except subprocess.CalledProcessError as e:
        print(f"Subprocess error: {e}")
        print(f"STDOUT:\n{e.stdout}")
        print(f"STDERR:\n{e.stderr}")
        raise e


run_subprocess([python, '-m', 'pip', 'install', '--upgrade', 'pip', 'setuptools', 'wheel', 'pyinstaller'])
run_subprocess([python, '-m', 'pip', 'install', '-r', '../src/requirements.txt'])
importlib.reload(site)
from PIL import Image


for file in os.listdir('../src'):
    print(os.path.abspath(os.path.join('../src', file)))

ffmpeg = subprocess.check_output([python, '-c', "from external import External; x = External.download_ffmpeg(); print(f'####{x}')"], cwd='../src').decode()
deno = subprocess.check_output([python, '-c', "from external import External; x = External.download_deno(); print(f'####{x}')"], cwd='../src').decode()


with open('../src/version.txt', 'w') as f:
    f.write(app_version)


FFMPEG_BIN_PATH = ffmpeg.split('####')[-1].strip()
DENO_BIN_PATH = deno.split('####')[-1].strip()

print(f'Building version {app_version} for {platform_name}')

print(FFMPEG_BIN_PATH)
print(DENO_BIN_PATH)

if os.path.exists('../dist'):
    shutil.rmtree('../dist')

args = [
    python,
    "-m", "PyInstaller",
    "--onefile",
    "--name", f'YT-DLP Web Player CLI-{app_version}-{platform_name}',
    "--add-binary", f"{FFMPEG_BIN_PATH}{colon}.",
    "--add-binary", f"{DENO_BIN_PATH}{colon}.",
    "--add-binary", f"src/version.txt{colon}.",
    "--add-data", f"src/static{colon}static",
    "--add-data", f"src/templates{colon}templates",
    "src/main.py"
]

run_subprocess(args, cwd='..')

with open('package.json', 'r') as f:
    pkg_json = f.read()
with open('package.json', 'w') as f:
    f.write(pkg_json.replace('1.0.0', app_version.removeprefix('v')))


img = Image.open('../src/static/favicon-template.png').convert('RGBA')
color = tuple(int("#ff7300"[i:i+2], 16) / 255 for i in (1, 3, 5))

data = img.getdata()
new_data = []
for item in data:
    new_data.append((int(item[0] * color[0]), int(item[1] * color[1]), int(item[2] * color[2]), item[3]))

img.putdata(new_data)
favicon48 = img.resize((48, 48), Image.Resampling.BICUBIC)
favicon256 = img.resize((256, 256), Image.Resampling.BICUBIC)
with open('favicon48.png', 'wb') as f:
    favicon48.save(f, format='PNG')
with open('favicon256.png', 'wb') as f:
    favicon256.save(f, format='PNG')


if os.name == 'nt':
    run_subprocess(["powershell", "-NoProfile", "-c", 'npm install'])
    run_subprocess(["powershell", "-NoProfile", "-c", 'npm run build'])
else:
    run_subprocess(['npm', 'install'])
    run_subprocess(['npm', 'run', 'build'])


zip_file_name = f'../dist/YT-DLP Web Player-{app_version}-{platform_name}.zip'

for i in os.listdir('./dist'):
    fullpath = os.path.join('./dist', i)
    if os.path.isdir(fullpath):
        if not 'unpacked' in i: continue
        print(f'zipping {fullpath} to {zip_file_name}')
        with zipfile.ZipFile(zip_file_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(fullpath):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, os.path.dirname(fullpath))
                    zipf.write(file_path, arcname)
                    print(f"Added: {arcname}")
    elif not i.endswith('yml'):
        print(f'copying {fullpath} to ../dist')
        shutil.copy(fullpath, f'../dist/YT-DLP Web Player-{app_version}-{platform_name}.{i.split(".")[-1]}')
