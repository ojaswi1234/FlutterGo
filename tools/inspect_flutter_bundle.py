#!/usr/bin/env python3
"""Inspect/extract Flutter Android debug assets from an APK or asset directory."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable

REQUIRED_DEBUG_FILES = (
    "kernel_blob.bin",
    "vm_snapshot_data",
    "isolate_snapshot_data",
)
ASSET_MANIFEST_CANDIDATES = (
    "AssetManifest.json",
    "AssetManifest.bin",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_asset_name(name: str) -> str | None:
    """Return a safe relative asset path; reject traversal/absolute entries."""
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        return None
    if path.parts[0] != "flutter_assets":
        return None
    return str(path)


def find_asset_root(source: Path) -> tuple[str, Path | zipfile.ZipFile]:
    if source.is_dir():
        candidates = [source / "flutter_assets", source]
        for candidate in candidates:
            if candidate.is_dir() and (candidate / "kernel_blob.bin").exists():
                return "directory", candidate
        raise FileNotFoundError(
            f"No flutter_assets directory containing kernel_blob.bin found under {source}"
        )
    if not source.is_file():
        raise FileNotFoundError(source)
    if not zipfile.is_zipfile(source):
        raise ValueError(f"Input is neither a directory nor a ZIP/APK: {source}")
    archive = zipfile.ZipFile(source)
    if not any(name.endswith("/flutter_assets/kernel_blob.bin") or name == "assets/flutter_assets/kernel_blob.bin" for name in archive.namelist()):
        archive.close()
        raise FileNotFoundError("APK/ZIP does not contain assets/flutter_assets/kernel_blob.bin")
    return "zip", archive


def iter_entries(kind: str, root: Path | zipfile.ZipFile) -> Iterable[tuple[str, bytes]]:
    if kind == "directory":
        assert isinstance(root, Path)
        for path in sorted(root.rglob("*")):
            if path.is_file():
                yield path.relative_to(root).as_posix(), path.read_bytes()
        return

    assert isinstance(root, zipfile.ZipFile)
    for info in sorted(root.infolist(), key=lambda item: item.filename):
        normalized = info.filename.replace("\\", "/")
        marker = "/flutter_assets/"
        if marker in normalized:
            rel = normalized.split(marker, 1)[1]
        elif normalized.startswith("assets/flutter_assets/"):
            rel = normalized[len("assets/flutter_assets/"):]
        else:
            continue
        safe = PurePosixPath(rel)
        if safe.is_absolute() or not safe.parts or any(part in ("", ".", "..") for part in safe.parts):
            continue
        if info.is_dir():
            continue
        yield safe.as_posix(), root.read(info)


def inspect(source: Path, output: Path) -> dict:
    kind, root = find_asset_root(source)
    output.mkdir(parents=True, exist_ok=True)
    asset_dir = output / "flutter_assets"
    asset_dir.mkdir(parents=True, exist_ok=True)

    files: list[dict] = []
    try:
        for rel, data in iter_entries(kind, root):
            destination = asset_dir.joinpath(*PurePosixPath(rel).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            files.append({
                "path": rel,
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            })
    finally:
        if isinstance(root, zipfile.ZipFile):
            root.close()

    names = {entry["path"] for entry in files}
    missing = [name for name in REQUIRED_DEBUG_FILES if name not in names]
    manifests = [name for name in ASSET_MANIFEST_CANDIDATES if name in names]
    report = {
        "input": str(source.resolve()),
        "input_kind": kind,
        "asset_count": len(files),
        "total_asset_bytes": sum(item["size_bytes"] for item in files),
        "required_debug_files": {
            name: {"present": name in names} for name in REQUIRED_DEBUG_FILES
        },
        "asset_manifests_found": manifests,
        "missing_required_debug_files": missing,
        "validation": "pass" if not missing else "incomplete-debug-bundle",
        "files": files,
    }
    (output / "bundle-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect", help="Inspect and extract a debug APK/assets directory")
    inspect_parser.add_argument("source", type=Path)
    inspect_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        report = inspect(args.source, args.output)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(f"Input: {report['input_kind']} — {report['input']}")
    print(f"Assets: {report['asset_count']} ({report['total_asset_bytes']} bytes)")
    print(f"Validation: {report['validation']}")
    if report["missing_required_debug_files"]:
        print("Missing: " + ", ".join(report["missing_required_debug_files"]))
        return 1
    print(f"Report: {args.output / 'bundle-report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
