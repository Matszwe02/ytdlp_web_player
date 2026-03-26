from datetime import datetime
import os
import shlex
import pip
import importlib

pip.main(shlex.split('install --upgrade GitPython'))

git = importlib.import_module('git')
path = os.path.abspath('.').removesuffix('/src')
latest_commit = git.Repo(path).head.commit
commit_date = datetime.fromtimestamp(latest_commit.committed_date)
commit_sha = latest_commit.hexsha[:4]
with open('version.txt', 'w') as f:
    f.write(commit_date.strftime('%Y-%m-%d') + ':' + commit_sha)