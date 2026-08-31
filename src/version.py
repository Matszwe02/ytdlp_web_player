from datetime import datetime
import os
import importlib
from external import External

External._pip_install('GitPython')

git = importlib.import_module('git')
path = os.path.abspath('.').removesuffix('/src')
repo = git.Repo(path)
latest_commit = repo.head.commit
commit_date = datetime.fromtimestamp(latest_commit.committed_date)
commit_sha = latest_commit.hexsha[:4]
version_string = commit_date.strftime('%Y-%m-%d') + ':' + commit_sha

for tag in repo.tags or []:
    if tag.commit == latest_commit:
        version_string = str(tag)

with open('version.txt', 'w') as f:
    f.write(version_string)
