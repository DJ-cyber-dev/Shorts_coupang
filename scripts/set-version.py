"""Set the same MAJOR.MINOR.PATCH version in all release-facing files."""
import argparse
from pathlib import Path
import re
import sys


VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
FILES = {
    "pyproject.toml": (re.compile(r'(?m)^version = "[^"]+"$'), 'version = "{version}"'),
    "src/shorts_studio/__init__.py": (re.compile(r'(?m)^__version__ = "[^"]+"$'), '__version__ = "{version}"'),
    "installer/ShortsStudio.iss": (re.compile(r"(?m)^AppVersion=[^\r\n]+$"), "AppVersion={version}"),
    "README.md": (re.compile(r"(?m)^# Shorts Studio [^\r\n]+$"), "# Shorts Studio {version}"),
}


def set_version(root: Path, version: str) -> None:
    if not VERSION.fullmatch(version):
        raise ValueError("Version must use MAJOR.MINOR.PATCH format, for example 0.2.1.")
    root = Path(root).resolve(strict=True)
    updates = {}
    for relative, (pattern, replacement) in FILES.items():
        path = root / relative
        source = path.read_text(encoding="utf-8")
        updated, count = pattern.subn(replacement.format(version=version), source)
        if count != 1:
            raise ValueError(f"Expected one version field in {relative}, found {count}.")
        updates[path] = updated
    for path, content in updates.items():
        temporary = path.with_suffix(path.suffix + ".version-tmp")
        temporary.write_text(content, encoding="utf-8", newline="")
        temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        set_version(args.root, args.version)
    except (OSError, ValueError) as exc:
        print(f"Version update failed: {exc}", file=sys.stderr)
        return 1
    print(f"Shorts Studio version set to {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
