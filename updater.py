import fnmatch
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
        v = extract_version(
            run_version_cmd([install_path] + version_args), version_regex
        )
        if v:
            return v
    return tool_config.get("installed_version", "0.0.0")


def _find_asset(release: dict, pattern: str) -> dict | None:
    for asset in release["assets"]:
        if fnmatch.fnmatch(asset["name"], pattern):
            return asset
    return None


def check_tool(
    tool_name: str, tool_config: dict, token: str | None = None
) -> UpdateResult:
    platform = config.get_platform()
    platforms = tool_config.get("platforms", {})
    if platform not in platforms:
        return UpdateResult(
            tool_name,
            "no_platform_config",
            error=f"No asset configured for platform '{platform}'",
        )
    platform_cfg = platforms[platform]
    installed = _get_installed_version(tool_config, platform_cfg)
    try:
        release = github_api.get_latest_release(tool_config["repo"], token)
    except Exception as e:
        return UpdateResult(tool_name, "error", error=str(e))
    latest_tag = release["tag_name"]
    latest_ver = normalize_version(latest_tag)
    if version_newer(latest_tag, installed):
        return UpdateResult(
            tool_name, "update_available", old_version=installed, new_version=latest_ver
        )
    return UpdateResult(
        tool_name, "up_to_date", old_version=installed, new_version=latest_ver
    )


def update_tool(
    tool_name: str, tool_config: dict, token: str | None = None, dry_run: bool = False
) -> UpdateResult:
    platform = config.get_platform()
    platforms = tool_config.get("platforms", {})
    if platform not in platforms:
        return UpdateResult(
            tool_name,
            "no_platform_config",
            error=f"No asset configured for platform '{platform}'",
        )

    platform_cfg = platforms[platform]
    binary_path = Path(platform_cfg["install_path"]).expanduser()
    binary_exists = binary_path.exists()
    installed = (
        _get_installed_version(tool_config, platform_cfg) if binary_exists else "0.0.0"
    )

    try:
        release = github_api.get_latest_release(tool_config["repo"], token)
    except Exception as e:
        return UpdateResult(tool_name, "error", error=str(e))

    latest_tag = release["tag_name"]
    latest_ver = normalize_version(latest_tag)

    if binary_exists and not version_newer(latest_tag, installed):
        return UpdateResult(
            tool_name, "up_to_date", old_version=installed, new_version=latest_ver
        )
    if dry_run:
        return UpdateResult(
            tool_name, "update_available", old_version=installed, new_version=latest_ver
        )

    asset = _find_asset(release, platform_cfg["asset_pattern"])
    if not asset:
        return UpdateResult(
            tool_name,
            "error",
            error=f"No asset matching '{platform_cfg['asset_pattern']}' "
            f"in release {latest_tag}",
        )

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
                return UpdateResult(
                    tool_name, "error", error="No files configured for extraction"
                )

            extracted_files: list[Path] = []
            for i, pattern in enumerate(file_patterns):
                member = archive.find_in_archive(archive_path, pattern)
                if not member:
                    return UpdateResult(
                        tool_name,
                        "error",
                        error=f"No file matching '{pattern}' in archive",
                    )

                dest_name = (
                    binary_names[i] if i < len(binary_names) else Path(member).name
                )
                dest = tmp / dest_name
                try:
                    archive.extract_file(archive_path, member, dest)
                    extracted_files.append(dest)
                except Exception as e:
                    return UpdateResult(
                        tool_name, "error", error=f"Extraction failed: {e}"
                    )
            extracted, extra_files = extracted_files[0], extracted_files[1:]
        else:
            extracted, extra_files = archive_path, []

        install_dir = binary_path.parent
        binaries_to_install = [(extracted, binary_path)]
        for extra in extra_files:
            binaries_to_install.append((extra, install_dir / extra.name))

        failed_binaries = []
        for src, dest in binaries_to_install:
            try:
                replace_binary(src, dest)
            except PermissionError:
                failed_binaries.append(
                    (dest.name, "Permission denied. You may need elevated privileges.")
                )
            except Exception as e:
                failed_binaries.append((dest.name, str(e)))

        if failed_binaries:
            err_msg = "; ".join(f"{name} ({err})" for name, err in failed_binaries)
            return UpdateResult(
                tool_name,
                "error",
                old_version=installed,
                new_version=latest_ver,
                error=f"Some binaries failed to replace: {err_msg}",
            )

    return UpdateResult(
        tool_name, "updated", old_version=installed, new_version=latest_ver
    )
