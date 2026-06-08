import os
from pathlib import Path

import requests

GITHUB_API = "https://api.github.com"


def _headers(token: str | None = None) -> dict:
    hdrs = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = token or os.environ.get("GITHUB_TOKEN")
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    return hdrs


def get_repo_description(repo: str, token: str | None = None) -> str | None:
    url = f"{GITHUB_API}/repos/{repo}"
    r = requests.get(url, headers=_headers(token), timeout=30)
    if r.status_code == 200:
        return r.json().get("description")
    return None


def get_latest_release(repo: str, token: str | None = None) -> dict:
    url = f"{GITHUB_API}/repos/{repo}/releases/latest"
    r = requests.get(url, headers=_headers(token), timeout=30)
    if r.status_code == 403 and "rate limit" in r.text.lower():
        raise RuntimeError(
            "GitHub API rate limit exceeded. Set the GITHUB_TOKEN environment variable "
            "or add github_token to [settings] in your config file."
        )
    if r.status_code == 404:
        raise RuntimeError(f"Repository '{repo}' not found or has no releases.")
    r.raise_for_status()
    return r.json()


def download_file(url: str, dest: Path, token: str | None = None) -> None:
    with requests.get(url, headers=_headers(token), stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        bar_width = 38
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total
                    filled = int(bar_width * pct)
                    bar = "#" * filled + "-" * (bar_width - filled)
                    print(
                        f"\r  [{bar}] {downloaded / 1048576:.1f}/{total / 1048576:.1f} MB",
                        end="",
                        flush=True,
                    )
        if total:
            print()
