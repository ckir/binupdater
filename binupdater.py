#!/usr/bin/env python3
"""binupdater — keep GitHub-released binaries up to date."""

import argparse
import fnmatch
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests
import tomli_w
from packaging.version import InvalidVersion, Version

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Version detection
# ---------------------------------------------------------------------------

_VERSION_ARGS = [["--version"], ["-V"], ["-v"], ["version"], ["--ver"]]


def detect_version(binary_path: str) -> tuple[list[str] | None, str | None, str | None]:
    for args in _VERSION_ARGS:
        cmd = [binary_path] + args
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            output = result.stdout + result.stderr
            m = re.search(DEFAULT_VERSION_REGEX, output)
            if m:
                return cmd, DEFAULT_VERSION_REGEX, m.group(1)
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


# ---------------------------------------------------------------------------
# Archive extraction
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Updater
# ---------------------------------------------------------------------------

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
        if fnmatch.fnmatch(asset["name"], pattern):
            return asset
    return None


def check_tool(tool_name: str, tool_config: dict, token: str | None = None) -> UpdateResult:
    platform = get_platform()
    platforms = tool_config.get("platforms", {})
    if platform not in platforms:
        return UpdateResult(tool_name, "no_platform_config",
                            error=f"No asset configured for platform '{platform}'")
    platform_cfg = platforms[platform]
    installed = _get_installed_version(tool_config, platform_cfg)
    try:
        release = get_latest_release(tool_config["repo"], token)
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
    platform = get_platform()
    platforms = tool_config.get("platforms", {})
    if platform not in platforms:
        return UpdateResult(tool_name, "no_platform_config",
                            error=f"No asset configured for platform '{platform}'")

    platform_cfg = platforms[platform]
    binary_path = Path(platform_cfg["install_path"]).expanduser()
    binary_exists = binary_path.exists()
    installed = _get_installed_version(tool_config, platform_cfg) if binary_exists else "0.0.0"

    try:
        release = get_latest_release(tool_config["repo"], token)
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
            download_file(asset["browser_download_url"], archive_path, token)
        except Exception as e:
            return UpdateResult(tool_name, "error", error=f"Download failed: {e}")

        if is_archive(archive_path):
            file_patterns = platform_cfg.get("files_in_archive") or []
            if not file_patterns:
                legacy = platform_cfg.get("binary_in_archive")
                file_patterns = [legacy] if legacy else []
            if not file_patterns:
                return UpdateResult(tool_name, "error", error="No files configured for extraction")

            extracted_files: list[Path] = []
            for pattern in file_patterns:
                member = find_in_archive(archive_path, pattern)
                if not member:
                    return UpdateResult(tool_name, "error",
                                        error=f"No file matching '{pattern}' in archive")
                dest = tmp / Path(member).name
                try:
                    extract_file(archive_path, member, dest)
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


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

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
    print("  Enter numbers separated by spaces — first selection is the main binary.")
    while True:
        raw = input("  > ").strip().replace(",", " ")
        parts = raw.split()
        indices: list[int] = []
        ok = True
        for p in parts:
            if p.isdigit() and 1 <= int(p) <= len(options):
                idx = int(p) - 1
                if idx not in indices:
                    indices.append(idx)
            else:
                print(f"  Invalid: '{p}'. Enter numbers between 1 and {len(options)}.")
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
    config = load_config()

    if tool_name in config.get("tools", {}) and not getattr(args, "force", False):
        print(f"'{tool_name}' is already tracked. Use 'update {tool_name}' to update it, or --force to reconfigure.")
        sys.exit(1)

    token = config.get("settings", {}).get("github_token") or os.environ.get("GITHUB_TOKEN")

    print(f"Fetching latest release for {repo}...")
    try:
        release = get_latest_release(repo, token)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)

    tag = release["tag_name"]
    print(f"Latest release: {release.get('name') or tag}  ({tag})\n")

    assets = [
        a for a in release["assets"]
        if not any(a["name"].endswith(s) for s in (".sha256", ".sha512", ".md5", ".asc", ".sig"))
    ]
    if not assets:
        print("No downloadable assets found in this release.")
        sys.exit(1)

    asset_names = [a["name"] for a in assets]
    current_platform = get_platform()

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
    extracted_bin: Path | None = None

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        default_install = config.get("settings", {}).get("default_install", {})
        win_dir = default_install.get("windows", "C:\\!PORTABLES\\!BIN")
        linux_dir = default_install.get("linux", "~/.bin").rstrip("/")

        for platform, asset in selected_assets.items():
            print(f"\n--- {platform} ---")
            print(f"Downloading {asset['name']}...")
            archive_path = tmp / asset["name"]
            try:
                download_file(asset["browser_download_url"], archive_path, token)
            except Exception as e:
                print(f"Error downloading: {e}")
                sys.exit(1)

            asset_pattern = _make_pattern(asset["name"], tag)

            if is_archive(archive_path):
                contents = list_archive(archive_path)
                print("Archive contents:")
                indices = _choose_multi(f"Select files to extract for {tool_name}", contents)
                chosen_files = [contents[i] for i in indices]
                file_patterns = [_make_pattern(f, tag) for f in chosen_files]
                print(f"  Main binary: {file_patterns[0]}")
                for extra in file_patterns[1:]:
                    print(f"  Extra file:  {extra}")
                platforms_config[platform] = {
                    "asset_pattern": asset_pattern,
                    "files_in_archive": file_patterns,
                }
                if platform == current_platform:
                    if not args.name:
                        tool_name = Path(chosen_files[0]).stem
                    member = find_in_archive(archive_path, file_patterns[0])
                    if member:
                        candidate = tmp / "extracted_binary"
                        try:
                            extract_file(archive_path, member, candidate)
                            extracted_bin = candidate
                        except Exception:
                            pass
            else:
                platforms_config[platform] = {"asset_pattern": asset_pattern}
                if platform == current_platform:
                    extracted_bin = archive_path

            print()
            install_defaults = {
                "windows": str(Path(win_dir) / f"{tool_name}.exe"),
                "linux": f"{linux_dir}/{tool_name}",
            }
            if platform == current_platform:
                found = shutil.which(tool_name)
                if found:
                    print(f"Found existing '{tool_name}': {found}")
                    install_path = _prompt("Installation path", found)
                else:
                    print(f"'{tool_name}' not found in PATH.")
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

        current_install_path = platforms_config[current_platform]["install_path"]

        if not Path(current_install_path).exists() and extracted_bin and extracted_bin.exists():
            ans = input(f"\n'{current_install_path}' does not exist. Install now? [Y/n]: ").strip().lower()
            if ans != "n":
                try:
                    replace_binary(extracted_bin, Path(current_install_path))
                    print(f"Installed to {current_install_path}")
                except PermissionError:
                    print("Permission denied. You may need elevated privileges.")

        print("\nDetecting installed version...")
        version_args: list[str] | None = None
        version_regex: str | None = None
        detected_version: str | None = None

        if Path(current_install_path).exists():
            version_cmd, version_regex, detected_version = detect_version(current_install_path)
            if version_cmd:
                version_args = version_cmd[1:]

        if not detected_version and extracted_bin and extracted_bin.exists():
            version_cmd, version_regex, detected_version = detect_version(str(extracted_bin))
            if version_cmd:
                version_args = version_cmd[1:]

        if detected_version:
            flags = " ".join(version_args or [])
            print(f"Detected version: {detected_version}  (via '{current_install_path} {flags}')")
        else:
            print("Could not auto-detect version.")
            flags_str = _prompt("Version flags", "--version")
            version_args = flags_str.split()
            version_regex = _prompt("Regex (group 1 = version)", DEFAULT_VERSION_REGEX)
            output = run_version_cmd([current_install_path] + version_args)
            detected_version = extract_version(output, version_regex)
            if detected_version:
                print(f"Detected version: {detected_version}")
            else:
                print("Still could not parse version — using release tag as baseline.")
                detected_version = normalize_version(tag)

        installed_version = detected_version or normalize_version(tag)

    tool_config = {
        "repo": repo,
        "version_args": version_args or ["--version"],
        "version_regex": version_regex or DEFAULT_VERSION_REGEX,
        "installed_version": installed_version,
        "platforms": platforms_config,
    }
    if "tools" not in config:
        config["tools"] = {}
    config["tools"][tool_name] = tool_config
    save_config(config)

    print(f"\nAdded '{tool_name}'")
    print(f"  Repo:    {repo}")
    for platform, pcfg in platforms_config.items():
        print(f"  [{platform}] {pcfg.get('install_path', '?')}")
    print(f"  Version: {installed_version}")
    print(f"  Config:  {get_config_path()}")


def cmd_update(args):
    config = load_config()
    tools = config.get("tools", {})
    if not tools:
        print("No tools tracked. Use 'add <github-url>' to add one.")
        return

    names = args.tools if args.tools else list(tools.keys())
    unknown = [n for n in names if n not in tools]
    if unknown:
        print(f"Unknown tools: {', '.join(unknown)}")
        sys.exit(1)

    token = config.get("settings", {}).get("github_token") or os.environ.get("GITHUB_TOKEN")
    check_only = getattr(args, "check", False)
    current_platform = get_platform()
    config_dirty = False

    results: list[UpdateResult] = []
    for name in names:
        print(f"\nChecking {name}...")
        tool_cfg = tools[name]
        platform_cfg = tool_cfg.get("platforms", {}).get(current_platform, {})

        if not check_only and platform_cfg:
            if _resolve_install_path(name, platform_cfg):
                config_dirty = True

        result = check_tool(name, tool_cfg, token) if check_only else update_tool(name, tool_cfg, token)
        results.append(result)

        if result.status == "updated":
            print(f"  Updated {result.old_version} -> {result.new_version}")
            config["tools"][name]["installed_version"] = result.new_version
        elif result.status == "up_to_date":
            print(f"  Up to date ({result.new_version})")
        elif result.status == "update_available":
            print(f"  Update available: {result.old_version} -> {result.new_version}")
        elif result.status == "no_platform_config":
            print(f"  Skipped: {result.error}")
        elif result.status == "error":
            print(f"  Error: {result.error}")

    if not check_only or config_dirty:
        save_config(config)

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
    config = load_config()
    tools = config.get("tools", {})
    if not tools:
        print("No tools tracked.")
        return
    current_platform = get_platform()
    col = [20, 35, 12]
    print(f"{'Tool':<{col[0]}} {'Repo':<{col[1]}} {'Version':<{col[2]}} Install path ({current_platform})")
    print("-" * (sum(col) + 60))
    for name, cfg in tools.items():
        platform_cfg = cfg.get("platforms", {}).get(current_platform, {})
        print(
            f"{name:<{col[0]}} "
            f"{cfg.get('repo', '?'):<{col[1]}} "
            f"{cfg.get('installed_version', '?'):<{col[2]}} "
            f"{platform_cfg.get('install_path', '?')}"
        )


def cmd_remove(args):
    config = load_config()
    if args.tool not in config.get("tools", {}):
        print(f"'{args.tool}' is not tracked.")
        sys.exit(1)
    ans = input(f"Remove '{args.tool}' from tracking? [y/N]: ").strip().lower()
    if ans != "y":
        print("Aborted.")
        return
    del config["tools"][args.tool]
    save_config(config)
    print(f"Removed '{args.tool}'. The binary on disk was not deleted.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

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
        {"add": cmd_add, "update": cmd_update, "list": cmd_list, "remove": cmd_remove}[args.command](args)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
