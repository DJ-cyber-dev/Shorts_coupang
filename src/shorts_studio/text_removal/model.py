import hashlib
import ctypes
import os
from pathlib import Path
import sys
import urllib.request


def _has_package_identity() -> bool:
    if os.name != "nt":
        return False
    try:
        length = ctypes.c_uint32(0)
        result = ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None)
        return result != 15700  # APPMODEL_ERROR_NO_PACKAGE
    except (AttributeError, OSError):
        return False


def model_dir() -> Path:
    """Return the shared OCR model cache without importing the OCR runtime."""
    configured = os.getenv("SHORTS_MODEL_DIR")
    if configured:
        return Path(configured)
    if _has_package_identity():
        executable_dir = Path(sys.executable).resolve().parent
        for candidate in (executable_dir, *executable_dir.parents[:5]):
            if (candidate / "AppxManifest.xml").is_file():
                return candidate / "models"
        return executable_dir / "models"
    local_app_data = os.getenv("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / ".cache"
    return root / "ShortsStudio" / "models"


def user_network_dir() -> Path:
    """Return EasyOCR's writable user-network directory.

    MSIX package contents are read-only, so runtime-created EasyOCR files must
    live under the current user's LocalAppData instead of the package folder.
    """
    configured = os.getenv("SHORTS_USER_NETWORK_DIR")
    if configured:
        return Path(configured)
    if _has_package_identity():
        local_app_data = os.getenv("LOCALAPPDATA")
        root = Path(local_app_data) if local_app_data else Path.home() / ".cache"
        return root / "ShortsStudio" / "models" / "user_network"
    return model_dir() / "user_network"


LAMA_FILENAME = "inpainting_lama_2025jan.onnx"
LAMA_URL = "https://huggingface.co/opencv/inpainting_lama/resolve/aee6d22/inpainting_lama_2025jan.onnx"
LAMA_BYTES = 92_591_623
LAMA_SHA256 = "7df918ac3921d3daf0aae1d219776cf0dc4e4935f035af81841b40adcf74fdf2"


def lama_model_path() -> Path:
    return model_dir() / LAMA_FILENAME


def prepare_lama_model() -> Path:
    """Fetch a pinned, hash-verified ONNX model during explicit setup only."""
    target = lama_model_path()
    if target.is_file() and target.stat().st_size == LAMA_BYTES:
        digest = hashlib.sha256()
        with target.open("rb") as existing:
            while chunk := existing.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() == LAMA_SHA256:
            return target

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    digest = hashlib.sha256()
    size = 0
    try:
        with urllib.request.urlopen(LAMA_URL, timeout=30) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > LAMA_BYTES:
                    raise RuntimeError("LaMa model download exceeded its expected size.")
                digest.update(chunk)
                output.write(chunk)
        actual_hash = digest.hexdigest()
        if size != LAMA_BYTES or actual_hash != LAMA_SHA256:
            raise RuntimeError(
                f"LaMa model validation failed at {target} "
                f"(size={size}, sha256={actual_hash[:16]}...)."
            )
        os.replace(temporary, target)
        return target
    finally:
        temporary.unlink(missing_ok=True)
