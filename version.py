from datetime import datetime
from git import Repo
latest_commit = Repo().head.commit
commit_date = datetime.fromtimestamp(latest_commit.committed_date)
with open('version.txt', 'w') as f:
    f.write(commit_date.strftime('%Y-%m-%d'))