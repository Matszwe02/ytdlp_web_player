from datetime import datetime
from git import Repo
latest_commit = Repo().head.commit
commit_date = datetime.fromtimestamp(latest_commit.committed_date)
commit_sha = latest_commit.hexsha[:4]
with open('version.txt', 'w') as f:
    f.write(commit_date.strftime('%Y-%m-%d') + ':' + commit_sha)