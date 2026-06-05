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
