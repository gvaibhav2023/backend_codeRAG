import os
import shutil
import time
from git import Repo, GitCommandError


def clone_repo_for_user(user_id: str, github_url: str) -> str:
    base_dir = f"app/repos/{user_id}"
    os.makedirs(base_dir, exist_ok=True)

    # 🔑 UNIQUE temp repo every time
    temp_repo = f"{base_dir}/temp_repo_{int(time.time())}"

    print(f"[CLONE] Cloning into: {temp_repo}")

    try:
        Repo.clone_from(github_url, temp_repo)
    except GitCommandError as e:
        raise RuntimeError(f"Git clone failed: {e}")

    return temp_repo
