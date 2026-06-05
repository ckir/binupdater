# binupdater.py Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose the monolithic 860+ line `binupdater.py` file into six smaller, cohesive, flat modules in the root folder to reduce agent token consumption and improve code quality.

**Architecture:** Split the codebase into five supporting modules (`config.py`, `github_api.py`, `archive.py`, `updater.py`, `cli.py`) and a lightweight `binupdater.py` entrypoint. Update the unit tests file to import from `cli.py` and run them to ensure 100% regression safety.

**Tech Stack:** Python 3 (standard library).

---

### Task 1: Create `config.py`

Create `config.py` to handle all configuration path, loading, saving, and platform detection logic.

**Files:**
- Create: `config.py`

- [ ] **Step 1: Create `config.py`**

Write the following content to `config.py`:

```python
import sys
import tomllib
from pathlib import Path
import tomli_w

_PROJECT_DIR = Path(__file__).parent
DEFAULT_VERSION_REGEX = r"(\d+\.\d+\.\d+(?:[.\-][a-zA-Z0-9]+)*)"


def get_config_path() -> Path:
    return _PROJECT_DIR / "config.toml"


_DEFAULT_CONFIG = """\
[settings]

[settings.default_install]
windows = "C:\\\\!PORTABLES\\\\!BIN"
linux = "~/.bin"

# Optional: set a GitHub token to avoid API rate limits
# github_token = "ghp_..."

[tools]
"""


def load_config() -> dict:
    path = get_config_path()
    if not path.exists():
        path.write_text(_DEFAULT_CONFIG, encoding="utf-8")
        print(f"Created default config: {path}")
    with open(path, "rb") as f:
        return tomllib.load(f)


def save_config(config: dict) -> None:
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(config, f)


def get_platform() -> str:
    if sys.platform == "win32":
        return "windows"
    elif sys.platform == "darwin":
        return "macos"
    return "linux"
```

- [ ] **Step 2: Run verification**

Run syntax check: `python -m py_compile config.py`  
Expected: No errors (exits with code 0)

- [ ] **Step 3: Commit**

```bash
git add config.py
git commit -m "refactor: extract config.py"
```

---

### Task 2: Create `github_api.py`

Create `github_api.py` to handle GitHub API calls and file downloads.

**Files:**
- Create: `github_api.py`

- [ ] **Step 1: Create `github_api.py`**

Write the following content to `github_api.py`:

```python
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
                        f"\r  [{bar}] {downloaded/1048576:.1f}/{total/1048576:.1f} MB",
                        end="", flush=True,
                    )
        if total:
            print()
```

- [ ] **Step 2: Run verification**

Run syntax check: `python -m py_compile github_api.py`  
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add github_api.py
git commit -m "refactor: extract github_api.py"
```

---

### Task 3: Create `archive.py`

Create `archive.py` to check, list, and extract files from zip/tar archives.

**Files:**
- Create: `archive.py`

- [ ] **Step 1: Create `archive.py`**

Write the following content to `archive.py`:

```python
import fnmatch
import tarfile
import zipfile
from pathlib import Path

_ARCHIVE_EXTS = (".zip", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")


def is_archive(path: Path) -> bool:
    return any(path.name.lower().endswith(ext) for ext in _ARCHIVE_EXTS)


def list_archive(path: Path) -> list[str]:
    name = path.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            return [m.filename for m in z.infolist() if not m.is_dir()]
    for ext in (".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"):
        if name.endswith(ext):
            with tarfile.open(path) as t:
                return [m.name for m in t.getmembers() if m.isfile()]
    return []


def find_in_archive(path: Path, pattern: str) -> str | None:
    for member in list_archive(path):
        if fnmatch.fnmatch(member, pattern):
            return member
    return None


def extract_file(archive_path: Path, member: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    name = archive_path.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as z:
            with z.open(member) as src, open(dest, "wb") as dst:
                dst.write(src.read())
    else:
        with tarfile.open(archive_path) as t:
            obj = t.extractfile(t.getmember(member))
            if obj:
                with open(dest, "wb") as dst:
                    dst.write(obj.read())
```

- [ ] **Step 2: Run verification**

Run syntax check: `python -m py_compile archive.py`  
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add archive.py
git commit -m "refactor: extract archive.py"
```

---

### Task 4: Create `updater.py`

Create `updater.py` containing version detection, version verification, file binary replacements, and the `UpdateResult` check/update tool logic.

**Files:**
- Create: `updater.py`

- [ ] **Step 1: Create `updater.py`**

Write the following content to `updater.py`:

```python
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from packaging.version import InvalidVersion, Version

import archive
import config
import github_api

_VERSION_ARGS = [["--version"], ["-V"], ["-v"], ["version"], ["--ver"]]


@dataclass
class UpdateResult:
    tool: str
    status: str  # updated | up_to_date | update_available | no_platform_config | error
    old_version: str | None = None
    new_version: str | None = None
    error: str | None = None


def _make_executable(path: Path) -> None:
    if sys.platform != "win32":
        path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def replace_binary(src: Path, dest: Path) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _make_executable(src)
    if sys.platform == "win32":
        backup = dest.with_suffix(dest.suffix + ".bak")
        if backup.exists():
            backup.unlink()
        if dest.exists():
            dest.rename(backup)
        try:
            shutil.copy2(src, dest)
            backup.unlink(missing_ok=True)
        except Exception:
            if backup.exists() and not dest.exists():
                backup.rename(dest)
            raise
    else:
        tmp = dest.with_name(dest.name + ".tmp_binupdater")
        shutil.copy2(src, tmp)
        _make_executable(tmp)
        tmp.rename(dest)


def detect_version(binary_path: str) -> tuple[list[str] | None, str | None, str | None]:
    for args in _VERSION_ARGS:
        cmd = [binary_path] + args
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            output = result.stdout + result.stderr
            m = re.search(config.DEFAULT_VERSION_REGEX, output)
            if m:
                return cmd, config.DEFAULT_VERSION_REGEX, m.group(1)
        except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError, OSError):
            continue
    return None, None, None


def run_version_cmd(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout + result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def extract_version(output: str, regex: str) -> str | None:
    m = re.search(regex, output)
    return m.group(1) if m else None


def version_newer(latest_tag: str, installed: str) -> bool:
    try:
        return Version(latest_tag.lstrip("v")) > Version(installed.lstrip("v"))
    except InvalidVersion:
        return latest_tag.lstrip("v") != installed.lstrip("v")


def normalize_version(tag: str) -> str:
    return tag.lstrip("v")


def _get_installed_version(tool_config: dict, platform_cfg: dict) -> str:
    install_path = str(Path(platform_cfg.get("install_path", "")).expanduser())
    version_args = tool_config.get("version_args", ["--version"])
    version_regex = tool_config.get("version_regex")
    if install_path and version_regex:
        v = extract_version(run_version_cmd([install_path] + version_args), version_regex)
        if v:
            return v
    return tool_config.get("installed_version", "0.0.0")


def _find_asset(release: dict, pattern: str) -> dict | None:
    for asset in release["assets"]:
        if fnmatch_fnmatch(asset["name"], pattern):
            import fnmatch
            # Wait, let's fix fnmatch usage: we should import fnmatch or use fnmatch.fnmatch
    return None
```
*(Wait, let's write `_find_asset` correctly using standard library `fnmatch` without standard issues)*
```python
import fnmatch

def _find_asset(release: dict, pattern: str) -> dict | None:
    for asset in release["assets"]:
        if fnmatch.fnmatch(asset["name"], pattern):
            return asset
    return None
```

Let's write the complete code for `updater.py` with the `check_tool` and `update_tool` functions fully implemented:

```python
def check_tool(tool_name: str, tool_config: dict, token: str | None = None) -> UpdateResult:
    platform = config.get_platform()
    platforms = tool_config.get("platforms", {})
    if platform not in platforms:
        return UpdateResult(tool_name, "no_platform_config",
                            error=f"No asset configured for platform '{platform}'")
    platform_cfg = platforms[platform]
    installed = _get_installed_version(tool_config, platform_cfg)
    try:
        release = github_api.get_latest_release(tool_config["repo"], token)
    except Exception as e:
        return UpdateResult(tool_name, "error", error=str(e))
    latest_tag = release["tag_name"]
    latest_ver = normalize_version(latest_tag)
    if version_newer(latest_tag, installed):
        return UpdateResult(tool_name, "update_available",
                            old_version=installed, new_version=latest_ver)
    return UpdateResult(tool_name, "up_to_date", old_version=installed, new_version=latest_ver)


def update_tool(
    tool_name: str, tool_config: dict, token: str | None = None, dry_run: bool = False
) -> UpdateResult:
    platform = config.get_platform()
    platforms = tool_config.get("platforms", {})
    if platform not in platforms:
        return UpdateResult(tool_name, "no_platform_config",
                            error=f"No asset configured for platform '{platform}'")

    platform_cfg = platforms[platform]
    binary_path = Path(platform_cfg["install_path"]).expanduser()
    binary_exists = binary_path.exists()
    installed = _get_installed_version(tool_config, platform_cfg) if binary_exists else "0.0.0"

    try:
        release = github_api.get_latest_release(tool_config["repo"], token)
    except Exception as e:
        return UpdateResult(tool_name, "error", error=str(e))

    latest_tag = release["tag_name"]
    latest_ver = normalize_version(latest_tag)

    if binary_exists and not version_newer(latest_tag, installed):
        return UpdateResult(tool_name, "up_to_date", old_version=installed, new_version=latest_ver)
    if dry_run:
        return UpdateResult(tool_name, "update_available",
                            old_version=installed, new_version=latest_ver)

    asset = _find_asset(release, platform_cfg["asset_pattern"])
    if not asset:
        return UpdateResult(tool_name, "error",
                            error=f"No asset matching '{platform_cfg['asset_pattern']}' "
                                  f"in release {latest_tag}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        archive_path = tmp / asset["name"]
        print(f"  Downloading {asset['name']}...")
        try:
            github_api.download_file(asset["browser_download_url"], archive_path, token)
        except Exception as e:
            return UpdateResult(tool_name, "error", error=f"Download failed: {e}")

        if archive.is_archive(archive_path):
            file_patterns = platform_cfg.get("files_in_archive") or []
            binary_names = platform_cfg.get("binary_names") or []
            if not file_patterns:
                legacy = platform_cfg.get("binary_in_archive")
                file_patterns = [legacy] if legacy else []
            if not file_patterns:
                return UpdateResult(tool_name, "error", error="No files configured for extraction")

            extracted_files: list[Path] = []
            for i, pattern in enumerate(file_patterns):
                member = archive.find_in_archive(archive_path, pattern)
                if not member:
                    return UpdateResult(tool_name, "error",
                                        error=f"No file matching '{pattern}' in archive")
                
                dest_name = binary_names[i] if i < len(binary_names) else Path(member).name
                dest = tmp / dest_name
                try:
                    archive.extract_file(archive_path, member, dest)
                    extracted_files.append(dest)
                except Exception as e:
                    return UpdateResult(tool_name, "error", error=f"Extraction failed: {e}")
            extracted, extra_files = extracted_files[0], extracted_files[1:]
        else:
            extracted, extra_files = archive_path, []

        install_dir = binary_path.parent
        try:
            replace_binary(extracted, binary_path)
            for extra in extra_files:
                replace_binary(extra, install_dir / extra.name)
        except PermissionError:
            return UpdateResult(tool_name, "error",
                                error=f"Permission denied writing to {install_dir}. "
                                      f"Try running with elevated privileges (sudo on Linux).")
        except Exception as e:
            return UpdateResult(tool_name, "error", error=f"Failed to replace binary: {e}")

    return UpdateResult(tool_name, "updated", old_version=installed, new_version=latest_ver)
```

- [ ] **Step 2: Run verification**

Run syntax check: `python -m py_compile updater.py`  
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add updater.py
git commit -m "refactor: extract updater.py"
```

---

### Task 5: Create `cli.py`

Create `cli.py` to hold user interface selections, prompts, helper logic, and CLI commands execution.

**Files:**
- Create: `cli.py`

- [ ] **Step 1: Create `cli.py`**

Write the following content to `cli.py`:

```python
import os
import sys
import re
import shutil
import tempfile
from pathlib import Path

import archive
import config
import github_api
import updater


def _prompt(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{label}{suffix}: ").strip()
    return val if val else (default or "")


def _choose(prompt: str, options: list[str], hint_substr: str | None = None) -> int:
    for i, opt in enumerate(options, 1):
        tag = "  <-- detected" if hint_substr and hint_substr.lower() in opt.lower() else ""
        print(f"  {i:3}. {opt}{tag}")
    while True:
        raw = input(f"{prompt} (1-{len(options)}): ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print(f"  Enter a number between 1 and {len(options)}.")


def _choose_multi(prompt: str, options: list[str]) -> list[int]:
    for i, opt in enumerate(options, 1):
        print(f"  {i:3}. {opt}")
    print(f"  {prompt}")
    print("  Enter numbers or ranges (e.g. 1-5,7,18-20) — first selection is the main binary.")
    while True:
        raw = input("  > ").strip()
        
        # Normalize: remove spaces around hyphens (e.g. "1 - 5" -> "1-5")
        raw = re.sub(r'\s*-\s*', '-', raw)
        
        # Split by commas or spaces
        parts = re.split(r'[,\s]+', raw)
        parts = [p for p in parts if p]  # filter out empty elements
        
        indices: list[int] = []
        ok = True
        
        for p in parts:
            if "-" in p:
                subparts = p.split("-")
                if len(subparts) == 2 and subparts[0].isdigit() and subparts[1].isdigit():
                    start, end = int(subparts[0]), int(subparts[1])
                    if 1 <= start <= len(options) and 1 <= end <= len(options):
                        # Support ranges both ascending and descending
                        step = 1 if start <= end else -1
                        for val in range(start, end + step, step):
                            idx = val - 1
                            if idx not in indices:
                                indices.append(idx)
                    else:
                        print(f"  Invalid range: '{p}'. Enter numbers between 1 and {len(options)}.")
                        ok = False
                        break
                else:
                    print(f"  Invalid format: '{p}'. Enter numbers or ranges like 1-5.")
                    ok = False
                    break
            elif p.isdigit():
                val = int(p)
                if 1 <= val <= len(options):
                    idx = val - 1
                    if idx not in indices:
                        indices.append(idx)
                else:
                    print(f"  Invalid: '{p}'. Enter numbers between 1 and {len(options)}.")
                    ok = False
                    break
            else:
                print(f"  Invalid format: '{p}'. Enter numbers or ranges like 1-5.")
                ok = False
                break
                
        if ok and indices:
            return indices
        if ok:
            print("  Select at least one file.")


def _parse_github_url(url: str) -> str:
    url = url.rstrip("/")
    m = re.search(r"github\.com[/:]([^/\s]+/[^/\s]+)", url)
    if not m:
        raise ValueError(f"Cannot parse GitHub URL: {url}")
    return m.group(1).removesuffix(".git")


def _make_pattern(name: str, tag: str) -> str:
    clean = tag.lstrip("v")
    for v in (tag, clean):
        if v in name:
            return name.replace(v, "*", 1)
    return name


def _resolve_install_path(tool_name: str, platform_cfg: dict) -> bool:
    install_path = platform_cfg.get("install_path", "")
    found = shutil.which(tool_name)
    if not found or not install_path:
        return False
    if Path(found).resolve() == Path(install_path).expanduser().resolve():
        return False
    print(f"  Found '{tool_name}' at {found}")
    print(f"  Config has install path: {install_path}")
    ans = input(f"  Use {found} instead? [Y/n]: ").strip().lower()
    if ans != "n":
        platform_cfg["install_path"] = found
        return True
    return False


def cmd_add(args):
    try:
        repo = _parse_github_url(args.url)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    tool_name = args.name or repo.split("/")[1]
    cfg_data = config.load_config()

    if tool_name in cfg_data.get("tools", {}) and not getattr(args, "force", False):
        print(f"'{tool_name}' is already tracked. Use 'update {tool_name}' to update it, or --force to reconfigure.")
        sys.exit(1)

    token = cfg_data.get("settings", {}).get("github_token") or os.environ.get("GITHUB_TOKEN")

    print(f"Fetching repository details for {repo}...")
    description = github_api.get_repo_description(repo, token)

    print(f"Fetching latest release for {repo}...")
    try:
        release = github_api.get_latest_release(repo, token)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)

    tag = release["tag_name"]
    print(f"Latest release: {release.get('name') or tag}  ({tag})")
    if description:
        print(f"About: {description}")
    print()

    assets = [
        a for a in release["assets"]
        if not any(a["name"].endswith(s) for s in (".sha256", ".sha512", ".md5", ".asc", ".sig"))
    ]
    if not assets:
        print("No downloadable assets found in this release.")
        sys.exit(1)

    asset_names = [a["name"] for a in assets]
    current_platform = config.get_platform()

    print("Available assets:")
    cur_idx = _choose(
        f"Select asset for {current_platform} (current platform)",
        asset_names,
        current_platform,
    )
    selected_assets: dict[str, dict] = {current_platform: assets[cur_idx]}
    print(f"  -> {assets[cur_idx]['name']}\n")

    other_platform = "linux" if current_platform == "windows" else "windows"
    if input(f"Configure {other_platform} asset too? [y/N]: ").strip().lower() == "y":
        print(f"\nAvailable assets (for {other_platform}):")
        other_idx = _choose(f"Select asset for {other_platform}", asset_names, other_platform)
        selected_assets[other_platform] = assets[other_idx]
        print(f"  -> {assets[other_idx]['name']}\n")

    platforms_config: dict[str, dict] = {}
    current_extracted: list[Path] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        default_install = cfg_data.get("settings", {}).get("default_install", {})
        win_dir = default_install.get("windows", "C:\\!PORTABLES\\!BIN")
        linux_dir = default_install.get("linux", "~/.bin").rstrip("/")

        for platform, asset in selected_assets.items():
            print(f"\n--- {platform} ---")
            print(f"Downloading {asset['name']}...")
            archive_path = tmp / asset["name"]
            try:
                github_api.download_file(asset["browser_download_url"], archive_path, token)
            except Exception as e:
                print(f"Error downloading: {e}")
                sys.exit(1)

            asset_pattern = _make_pattern(asset["name"], tag)
            binary_names = []

            if archive.is_archive(archive_path):
                contents = archive.list_archive(archive_path)
                print("Archive contents:")
                indices = _choose_multi(f"Select files to extract for {tool_name}", contents)
                chosen_files = [contents[i] for i in indices]
                
                for i, f in enumerate(chosen_files):
                    archive_name = Path(f).name
                    prompt_label = "Install as name" if i == 0 else f"Install '{archive_name}' as"
                    new_name = _prompt(prompt_label, archive_name)
                    binary_names.append(new_name)

                file_patterns = [_make_pattern(f, tag) for f in chosen_files]
                print(f"  Main binary: {file_patterns[0]}")
                for extra in file_patterns[1:]:
                    print(f"  Extra file:  {extra}")
                
                platforms_config[platform] = {
                    "asset_pattern": asset_pattern,
                    "files_in_archive": file_patterns,
                    "binary_names": binary_names,
                }
                if platform == current_platform:
                    if not args.name:
                        tool_name = Path(binary_names[0]).stem
                    for i, pattern in enumerate(file_patterns):
                        member = archive.find_in_archive(archive_path, pattern)
                        if member:
                            dest = tmp / binary_names[i]
                            try:
                                archive.extract_file(archive_path, member, dest)
                                current_extracted.append(dest)
                            except Exception:
                                pass
            else:
                archive_name = asset["name"]
                new_name = _prompt("Install as name", archive_name)
                binary_names = [new_name]
                platforms_config[platform] = {
                    "asset_pattern": asset_pattern,
                    "binary_names": binary_names,
                }
                if platform == current_platform:
                    if not args.name:
                        tool_name = Path(new_name).stem
                    current_extracted.append(archive_path)

            print()
            install_defaults = {
                "windows": str(Path(win_dir) / f"{tool_name}.exe"),
                "linux": f"{linux_dir}/{tool_name}",
            }
            if platform == current_platform:
                found = shutil.which(binary_names[0])
                if found:
                    print(f"Found existing '{binary_names[0]}': {found}")
                    install_path = _prompt("Installation path", found)
                else:
                    print(f"'{binary_names[0]}' not found in PATH.")
                    install_path = _prompt(
                        "Installation path",
                        install_defaults.get(platform, f"/usr/local/bin/{tool_name}"),
                    )
            else:
                install_path = _prompt(
                    f"Default install path for {platform}",
                    install_defaults.get(platform, f"/usr/local/bin/{tool_name}"),
                )
            platforms_config[platform]["install_path"] = install_path
            
            # Additional binaries
            if platform == current_platform:
                all_install_paths = [install_path]
                install_dir = Path(install_path).parent
                for extra_name in binary_names[1:]:
                    found_extra = shutil.which(extra_name)
                    if found_extra:
                        print(f"Found existing '{extra_name}': {found_extra}")
                        extra_path = _prompt(f"Installation path for '{extra_name}'", found_extra)
                    else:
                        extra_path = _prompt(f"Installation path for '{extra_name}'", str(install_dir / extra_name))
                    all_install_paths.append(extra_path)
                current_install_paths = all_install_paths
            else:
                pass

        if current_extracted:
            main_dest = Path(current_install_paths[0])
            print(f"\nTarget installation for '{tool_name}':")
            for i, p in enumerate(current_install_paths):
                print(f"  {binary_names[i]:<20} -> {p}")

            # Check which files are missing
            missing = [p for p in current_install_paths if not Path(p).exists()]
            
            if missing:
                print(f"\nSome files are missing from their target locations: {', '.join(Path(p).name for p in missing)}")
                ans = input(f"Install all {len(current_extracted)} files now? [Y/n]: ").strip().lower()
            else:
                ans = input(f"\nAll files already exist. Reinstall/Overwrite all {len(current_extracted)} files? [y/N]: ").strip().lower()
                if not ans: ans = "n"

            if (missing and ans != "n") or (not missing and ans == "y"):
                try:
                    for i, src in enumerate(current_extracted):
                        dest = Path(current_install_paths[i])
                        updater.replace_binary(src, dest)
                    print(f"Installed to {main_dest.parent}")
                except PermissionError:
                    print("Permission denied. You may need elevated privileges.")
                except Exception as e:
                    print(f"Error during installation: {e}")

        current_install_path = current_install_paths[0]

        print("\nDetecting installed version...")
        version_args: list[str] | None = None
        version_regex: str | None = None
        detected_version: str | None = None

        if Path(current_install_path).exists():
            version_cmd, version_regex, detected_version = updater.detect_version(current_install_path)
            if version_cmd:
                version_args = version_cmd[1:]

        if not detected_version and current_extracted:
            version_cmd, version_regex, detected_version = updater.detect_version(str(current_extracted[0]))
            if version_cmd:
                version_args = version_cmd[1:]

        if detected_version:
            flags = " ".join(version_args or [])
            print(f"Detected version: {detected_version}  (via '{current_install_path} {flags}')")
        else:
            print("Could not auto-detect version.")
            flags_str = _prompt("Version flags", "--version")
            version_args = flags_str.split()
            version_regex = _prompt("Regex (group 1 = version)", config.DEFAULT_VERSION_REGEX)
            output = updater.run_version_cmd([current_install_path] + version_args)
            detected_version = updater.extract_version(output, version_regex)
            if detected_version:
                print(f"Detected version: {detected_version}")
            else:
                print("Still could not parse version — using release tag as baseline.")
                detected_version = updater.normalize_version(tag)

        installed_version = detected_version or updater.normalize_version(tag)

    tool_config = {
        "repo": repo,
        "description": description or "",
        "version_args": version_args or ["--version"],
        "version_regex": version_regex or config.DEFAULT_VERSION_REGEX,
        "installed_version": installed_version,
        "platforms": platforms_config,
    }
    if "tools" not in cfg_data:
        cfg_data["tools"] = {}
    cfg_data["tools"][tool_name] = tool_config
    config.save_config(cfg_data)

    print(f"\nAdded '{tool_name}'")
    print(f"  Repo:    {repo}")
    for platform, pcfg in platforms_config.items():
        print(f"  [{platform}] {pcfg.get('install_path', '?')}")
    print(f"  Version: {installed_version}")
    print(f"  Config:  {config.get_config_path()}")


def cmd_update(args):
    cfg_data = config.load_config()
    tools = cfg_data.get("tools", {})
    if not tools:
        print("No tools tracked. Use 'add <github-url>' to add one.")
        return

    names = args.tools if args.tools else list(tools.keys())
    unknown = [n for n in names if n not in tools]
    if unknown:
        print(f"Unknown tools: {', '.join(unknown)}")
        sys.exit(1)

    token = cfg_data.get("settings", {}).get("github_token") or os.environ.get("GITHUB_TOKEN")
    check_only = getattr(args, "check", False)
    current_platform = config.get_platform()
    config_dirty = False

    results: list[updater.UpdateResult] = []
    for name in names:
        print(f"\nChecking {name}...")
        tool_cfg = tools[name]
        platform_cfg = tool_cfg.get("platforms", {}).get(current_platform, {})

        if not check_only and platform_cfg:
            if _resolve_install_path(name, platform_cfg):
                config_dirty = True

        result = updater.check_tool(name, tool_cfg, token) if check_only else updater.update_tool(name, tool_cfg, token)
        results.append(result)

        if result.status == "updated":
            print(f"  Updated {result.old_version} -> {result.new_version}")
            cfg_data["tools"][name]["installed_version"] = result.new_version
        elif result.status == "up_to_date":
            print(f"  Up to date ({result.new_version})")
        elif result.status == "update_available":
            print(f"  Update available: {result.old_version} -> {result.new_version}")
        elif result.status == "no_platform_config":
            print(f"  Skipped: {result.error}")
        elif result.status == "error":
            print(f"  Error: {result.error}")

    if not check_only or config_dirty:
        config.save_config(cfg_data)

    parts = []
    if n := sum(1 for r in results if r.status == "updated"):
        parts.append(f"{n} updated")
    if n := sum(1 for r in results if r.status == "up_to_date"):
        parts.append(f"{n} up to date")
    if n := sum(1 for r in results if r.status == "update_available"):
        parts.append(f"{n} updates available")
    if n := sum(1 for r in results if r.status == "error"):
        parts.append(f"{n} error(s)")
    print(f"\nDone: {', '.join(parts) or 'nothing to do'}")


def cmd_list(args):
    cfg_data = config.load_config()
    tools = cfg_data.get("tools", {})
    if not tools:
        print("No tools tracked.")
        return
    current_platform = config.get_platform()
    col = [15, 25, 12, 40]
    print(f"{'Tool':<{col[0]}} {'Repo':<{col[1]}} {'Version':<{col[2]}} {'Description':<{col[3]}} Install path ({current_platform})")
    print("-" * (sum(col) + 40))
    for name, cfg in tools.items():
        platform_cfg = cfg.get("platforms", {}).get(current_platform, {})
        desc = cfg.get("description", "")
        if len(desc) > col[3] - 3:
            desc = desc[:col[3] - 3] + "..."
        
        install_path = platform_cfg.get("install_path", "?")
        binary_names = platform_cfg.get("binary_names", [])
        
        path_str = install_path
        if len(binary_names) > 1:
            install_dir = Path(install_path).parent
            paths = [install_path] + [str(install_dir / n) for n in binary_names[1:]]
            path_str = ", ".join(paths)

        print(
            f"{name:<{col[0]}} "
            f"{cfg.get('repo', '?'):<{col[1]}} "
            f"{cfg.get('installed_version', '?'):<{col[2]}} "
            f"{desc:<{col[3]}} "
            f"{path_str}"
        )


def cmd_remove(args):
    cfg_data = config.load_config()
    if args.tool not in cfg_data.get("tools", {}):
        print(f"'{args.tool}' is not tracked.")
        sys.exit(1)
    ans = input(f"Remove '{args.tool}' from tracking? [y/N]: ").strip().lower()
    if ans != "y":
        print("Aborted.")
        return
    del cfg_data["tools"][args.tool]
    config.save_config(cfg_data)
    print(f"Removed '{args.tool}'. The binary on disk was not deleted.")
```

- [ ] **Step 2: Run verification**

Run syntax check: `python -m py_compile cli.py`  
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add cli.py
git commit -m "refactor: extract cli.py"
```

---

### Task 6: Recreate `binupdater.py` as Entrypoint

Over-write `binupdater.py` with the lightweight entrypoint logic.

**Files:**
- Modify: `binupdater.py`

- [ ] **Step 1: Rewrite `binupdater.py`**

Over-write `binupdater.py` with the following content:

```python
#!/usr/bin/env python3
"""binupdater — keep GitHub-released binaries up to date."""

import argparse
import sys
import cli


def main():
    parser = argparse.ArgumentParser(
        prog="binupdater",
        description="Keep GitHub-released binaries up to date.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    p_add = sub.add_parser("add", help="Add a new tool to track")
    p_add.add_argument("url", help="GitHub repository URL")
    p_add.add_argument("--name", help="Override the tool name (defaults to repo name)")
    p_add.add_argument("--force", action="store_true", help="Re-add and overwrite existing configuration")

    p_update = sub.add_parser("update", help="Update tracked tools")
    p_update.add_argument("tools", nargs="*", metavar="TOOL", help="Tools to update (default: all)")
    p_update.add_argument("--check", action="store_true", help="Report available updates without installing")

    sub.add_parser("list", help="List tracked tools and their versions")

    p_remove = sub.add_parser("remove", help="Stop tracking a tool")
    p_remove.add_argument("tool", help="Tool name")

    args = parser.parse_args()
    try:
        cmd_func = {
            "add": cli.cmd_add,
            "update": cli.cmd_update,
            "list": cli.cmd_list,
            "remove": cli.cmd_remove,
        }[args.command]
        cmd_func(args)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run verification**

Run syntax check: `python -m py_compile binupdater.py`  
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add binupdater.py
git commit -m "refactor: turn binupdater.py into entrypoint"
```

---

### Task 7: Redirect Unit Tests to `cli.py`

We will modify `test_binupdater.py` to import `_choose_multi` from `cli.py` instead of `binupdater.py` and run tests.

**Files:**
- Modify: `test_binupdater.py`

- [ ] **Step 1: Edit `test_binupdater.py`**

In `test_binupdater.py`, change line 3 from:
```python
from binupdater import _choose_multi
```
to:
```python
from cli import _choose_multi
```

- [ ] **Step 2: Run verification**

Run tests: `python -m unittest test_binupdater.py`  
Expected: PASS (All 6 tests pass successfully)

- [ ] **Step 3: Commit**

```bash
git add test_binupdater.py
git commit -m "refactor: update unit tests imports"
```

---

### Task 8: Cleanup & End-to-End Verification

Ensure all files compile, run complete test suites, and confirm VCS is clean.

**Files:**
- Modify: None (verification only)

- [ ] **Step 1: Run entire unit test suite**

Run: `python -m unittest test_binupdater.py`  
Expected: PASS

- [ ] **Step 2: Confirm git workspace is clean**

Run: `git status`  
Expected: "nothing to commit, working tree clean"
