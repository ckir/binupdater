# binupdater

Keep GitHub-released binaries up to date across Windows and Linux/WSL.

## Requirements

- Python 3.11+
- A virtual environment (venv) is required to install dependencies

## Setup

### Windows

```powershell
cd C:\path\to\binupdater

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
```

### Linux / WSL

```bash
cd /path/to/binupdater   # or /mnt/c/... from WSL

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

> In WSL you may need to install the venv package first:
> `sudo apt install python3.XX-venv`

---

## Configuration

`config.toml` is created automatically on first run next to the script.
Edit it to change default install directories or add a GitHub token:

```toml
[settings]

[settings.default_install]
windows = "C:\!PORTABLES\!BIN"
linux = "~/.bin"

# Avoids GitHub API rate limits (60 req/h unauthenticated vs 5000 authenticated)
# github_token = "ghp_..."

[tools]
```

---

## Usage

### Add a tool

```
python binupdater.py add https://github.com/sharkdp/fd
```

Walk-through:
1. Fetches the latest GitHub release and lists all assets
2. You select the asset for the current platform
3. Optionally configure the other platform (Windows ↔ Linux) — each is downloaded and inspected
4. For each archive you pick which file(s) to extract (first = main binary, extras go to the same directory)
5. Confirm or change the install path (defaults from `config.toml`)
6. Version is auto-detected from the installed binary

Options:
- `--name <name>` — override the tool name (defaults to the repo name)
- `--force` — reconfigure a tool that is already tracked

### Update tools

```
python binupdater.py update              # update all tracked tools
python binupdater.py update fd rg        # update specific tools
python binupdater.py update --check      # check for updates without installing
```

If a binary is missing from disk it will be downloaded and installed regardless of the recorded version.

### List tracked tools

```
python binupdater.py list
```

### Remove a tool

```
python binupdater.py remove fd
```

Removes the tool from tracking only. The binary on disk is not deleted.

---

## Running from Windows (updates Linux/WSL binaries)

Use the provided batch file to run binupdater under WSL without opening a WSL terminal:

```
binupdater.bat update
binupdater.bat list
```

The batch file automatically sets the working directory so `config.toml` is always found correctly.

## Running from Linux / WSL (global access)

Symlink `binupdater.sh` into your PATH for system-wide access:

```bash
ln -s "$(readlink -f binupdater.sh)" ~/.local/bin/binupdater
chmod +x binupdater.sh
```

Then from anywhere:

```bash
binupdater update
```

> If the script lives on a Windows-mounted filesystem (`/mnt/c/...`), `chmod` may not persist.
> In that case add an alias to `~/.bashrc` instead:
> ```bash
> alias binupdater='bash /mnt/c/path/to/binupdater/binupdater.sh'
> ```

---

## GitHub API rate limits

Unauthenticated requests are limited to 60 per hour. If you track many tools or run updates frequently, add a token:

1. Create a token at https://github.com/settings/tokens (no scopes needed for public repos)
2. Add it to `config.toml`:
   ```toml
   [settings]
   github_token = "ghp_..."
   ```
   Or export it as an environment variable:
   ```
   GITHUB_TOKEN=ghp_...
   ```

---

## config.toml reference

```toml
[settings]
# github_token = "ghp_..."          # optional GitHub token

[settings.default_install]
windows = "C:\tools"                # default install directory for Windows
linux = "~/.bin"                    # default install directory for Linux

[tools.fd]
repo = "sharkdp/fd"
version_args = ["--version"]        # flags passed to the binary to get its version
version_regex = "(\\d+\\.\\d+\\.\\d+)"
installed_version = "10.4.2"

[tools.fd.platforms.windows]
asset_pattern = "fd-*-x86_64-pc-windows-msvc.zip"
files_in_archive = ["fd-*/fd.exe"]  # first entry = main binary
install_path = "C:\\tools\\fd.exe"

[tools.fd.platforms.linux]
asset_pattern = "fd-*-x86_64-unknown-linux-musl.tar.gz"
files_in_archive = ["fd-*/fd"]
install_path = "~/.bin/fd"
```
