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
