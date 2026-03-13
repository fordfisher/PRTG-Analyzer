from __future__ import annotations

from pathlib import Path
import zipfile
from typing import Any, Dict, Iterable


def version_tuple(value: str) -> tuple:
    return tuple(int(part) for part in value.lstrip("v").split("."))


def pick_zip_download_url(assets: Iterable[Dict[str, Any]]) -> str:
    for asset in assets:
        if str(asset.get("name", "")).endswith(".zip"):
            return str(asset.get("browser_download_url", ""))
    return ""


def build_release_result(current_version: str, release_data: Dict[str, Any]) -> Dict[str, Any]:
    tag = str(release_data.get("tag_name", ""))
    latest = tag.lstrip("v")
    zip_url = pick_zip_download_url(release_data.get("assets", []))
    up_to_date = version_tuple(current_version) >= version_tuple(latest) if latest else True
    return {
        "current": current_version,
        "latest": latest,
        "up_to_date": up_to_date,
        "download_url": zip_url,
        "release_url": str(release_data.get("html_url", "")),
    }


def extract_update_zip(zip_path: Path, parent_dir: Path, new_dir: Path, current_dir: Path) -> None:
    with zipfile.ZipFile(str(zip_path), "r") as archive:
        archive.extractall(str(parent_dir))

    if new_dir.exists():
        return

    extracted = [d for d in parent_dir.iterdir() if d.is_dir() and d.name.startswith("PyPRTG_CLA")]
    for directory in extracted:
        if directory != current_dir and directory.name != zip_path.stem:
            directory.rename(new_dir)
            break


def resolve_executable_path(new_dir: Path, new_ver: str) -> Path:
    exe_path = new_dir / f"PyPRTG_CLA_v{new_ver}.exe"
    if exe_path.exists():
        return exe_path
    return new_dir / "PyPRTG_CLA.exe"
