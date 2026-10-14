"""Create the Ed25519-signed manifest uploaded alongside a GitHub Release ZIP."""
import argparse
import base64
import getpass
import hashlib
from pathlib import Path
import re
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


DOMAIN = b"shorts-studio-update-v1\n"
ASSET = "ShortsStudio-Portable.zip"
VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def create_manifest(version: str, archive: Path, private_key_path: Path, output: Path) -> None:
    if not VERSION.fullmatch(version):
        raise ValueError("Version must use MAJOR.MINOR.PATCH format without a v prefix.")
    archive = archive.resolve(strict=True)
    if archive.name != ASSET:
        raise ValueError(f"The release archive must be named {ASSET}.")
    key_path = private_key_path.resolve(strict=True)
    project_root = Path(__file__).resolve().parents[1]
    if key_path.is_relative_to(project_root):
        raise ValueError("Keep the release signing key outside the repository.")
    passphrase = getpass.getpass("Release signing key passphrase: ").encode("utf-8")
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=passphrase)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("The release signing key must be an Ed25519 PEM private key.")
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    sha256 = digest.hexdigest()
    signature = key.sign(DOMAIN + f"{version}\n{ASSET}\n{sha256}\n".encode("ascii"))
    encoded_signature = base64.b64encode(signature).decode("ascii")
    text = ("{\n"
            f'  "version": "{version}",\n'
            f'  "asset": "{ASSET}",\n'
            f'  "sha256": "{sha256}",\n'
            f'  "signature": "{encoded_signature}"\n'
            "}\n")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Release version, for example 0.2.1")
    parser.add_argument("archive", type=Path, help=ASSET)
    parser.add_argument("private_key", type=Path, help="Ed25519 PEM private key stored outside this repository")
    parser.add_argument("--output", type=Path, default=Path("shorts-studio-update.json"))
    args = parser.parse_args()
    try:
        create_manifest(args.version, args.archive, args.private_key, args.output)
    except (OSError, ValueError) as exc:
        print(f"Manifest generation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Signed update manifest: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
