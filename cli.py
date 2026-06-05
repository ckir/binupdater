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
                succeeded = []
                failed = []
                for i, src in enumerate(current_extracted):
                    dest = Path(current_install_paths[i])
                    try:
                        updater.replace_binary(src, dest)
                        succeeded.append((src.name, dest))
                    except PermissionError:
                        print(f"  Error: Permission denied writing to {dest.name}.")
                        failed.append((dest, "Permission denied. You may need elevated privileges."))
                    except Exception as e:
                        print(f"  Error: Failed to replace {dest.name}: {e}")
                        failed.append((dest, str(e)))

                if succeeded:
                    print(f"Installed {len(succeeded)} file(s) to {main_dest.parent}")
                if failed:
                    print("\n[!] Summary of Failed Extractions/Installations:")
                    for dest, err in failed:
                        print(f"  - {dest}: {err}")

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

    failed_updates = [r for r in results if r.status == "error"]
    if failed_updates:
        print("\n--- Summary of Failed Updates ---")
        for r in failed_updates:
            print(f"  Tool: {r.tool}")
            print(f"    Error: {r.error}")


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
