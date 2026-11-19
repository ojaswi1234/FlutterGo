#!/usr/bin/env python3
"""Create and validate Flutter Go .fgbundle archives (format v1).

This is a transport/inspection format only. It does NOT make the Flutter
engine capable of executing an external bundle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

FORMAT_VERSION = 1
MANIFEST_PATH = "flutter_go/manifest.json"
REQUIRED_FILES = ("kernel_blob.bin", "vm_snapshot_data", "isolate_snapshot_data")
MAX_ENTRIES = 50_000
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024


class BundleError(Exception):
    """Invalid or unsafe Flutter Go bundle."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_relative_path(raw: str) -> str:
    if not isinstance(raw, str):
        raise BundleError("Bundle paths must be strings")
    normalized = raw.replace("\\", "/")
    raw_parts = normalized.split("/")
    path = PurePosixPath(normalized)
    if (not normalized or path.is_absolute() or any(part in ("", ".", "..") for part in raw_parts)):
        raise BundleError(f"Unsafe bundle path: {raw!r}")
    if "\x00" in normalized or re.match(r"^[A-Za-z]:", normalized):
        raise BundleError(f"Unsafe bundle path: {raw!r}")
    return path.as_posix()


def _file_records(asset_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(asset_root.rglob("*")):
        if path.is_symlink():
            raise BundleError(f"Symlinks are not allowed in bundles: {path}")
        if not path.is_file():
            continue
        rel = safe_relative_path(path.relative_to(asset_root).as_posix())
        data = path.read_bytes()
        records.append({"path": rel, "size_bytes": len(data), "sha256": sha256_bytes(data)})
    if not records:
        raise BundleError("Flutter asset directory is empty")
    return records


def pack_bundle(
    asset_root: Path,
    output: Path,
    project_name: str,
    flutter_version: str = "unknown",
    dart_version: str = "unknown",
    framework_revision: str = "unknown",
    engine_revision: str = "unknown",
) -> dict[str, Any]:
    asset_root = asset_root.resolve()
    if not asset_root.is_dir():
        raise BundleError(f"Asset root is not a directory: {asset_root}")

    records = _file_records(asset_root)
    by_name = {record["path"] for record in records}
    missing = [name for name in REQUIRED_FILES if name not in by_name]
    if missing:
        raise BundleError("Incomplete debug bundle; missing: " + ", ".join(missing))

    manifest: dict[str, Any] = {
        "format": "flutter-go-bundle",
        "format_version": FORMAT_VERSION,
        "project": {"name": project_name},
        "toolchain": {
            "flutter_version": flutter_version,
            "dart_version": dart_version,
            "framework_revision": framework_revision,
            "engine_revision": engine_revision,
            "build_mode": "debug",
        },
        "runtime_requirements": {
            "platform": "android",
            "execution_mode": "jit-debug",
            "native_plugins": "host-provided-only",
        },
        "asset_root": "flutter_assets",
        "files": records,
        "totals": {
            "file_count": len(records),
            "uncompressed_bytes": sum(item["size_bytes"] for item in records),
        },
        "limitations": [
            "Transport format only; does not establish runtime compatibility.",
            "Native plugin implementations must already exist in the host.",
            "Only debug/JIT artifacts are accepted by this POC format.",
        ],
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr(MANIFEST_PATH, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            for record in records:
                source = asset_root.joinpath(*PurePosixPath(record["path"]).parts)
                archive.write(source, f"flutter_assets/{record['path']}")
        tmp.replace(output)
    finally:
        if tmp.exists():
            tmp.unlink()
    return manifest


def _read_manifest(archive: zipfile.ZipFile) -> dict[str, Any]:
    names = archive.namelist()
    if names.count(MANIFEST_PATH) != 1:
        raise BundleError("Bundle must contain exactly one flutter_go/manifest.json")
    info = archive.getinfo(MANIFEST_PATH)
    if info.file_size > MAX_MANIFEST_BYTES:
        raise BundleError("Manifest exceeds size limit")
    try:
        manifest = json.loads(archive.read(MANIFEST_PATH))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"Invalid manifest JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise BundleError("Manifest root must be an object")
    if manifest.get("format") != "flutter-go-bundle":
        raise BundleError("Unrecognized bundle format")
    if manifest.get("format_version") != FORMAT_VERSION:
        raise BundleError(f"Unsupported format version: {manifest.get('format_version')!r}")
    toolchain = manifest.get("toolchain")
    if not isinstance(toolchain, dict) or toolchain.get("build_mode") != "debug":
        raise BundleError("Only debug bundles are supported by format v1")
    if not isinstance(manifest.get("files"), list):
        raise BundleError("Manifest 'files' must be an array")
    return manifest


def verify_bundle(bundle: Path) -> dict[str, Any]:
    if not zipfile.is_zipfile(bundle):
        raise BundleError(f"Not a ZIP/.fgbundle archive: {bundle}")
    with zipfile.ZipFile(bundle) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ENTRIES:
            raise BundleError(f"Archive has too many entries ({len(infos)})")
        if len({info.filename for info in infos}) != len(infos):
            raise BundleError("Archive contains duplicate entry names")
        total = sum(info.file_size for info in infos)
        if total > MAX_UNCOMPRESSED_BYTES:
            raise BundleError("Archive exceeds uncompressed size limit")

        manifest = _read_manifest(archive)
        expected: dict[str, dict[str, Any]] = {}
        for record in manifest.get("files", []):
            if not isinstance(record, dict):
                raise BundleError("Each manifest file record must be an object")
            rel = safe_relative_path(record.get("path", ""))
            size = record.get("size_bytes")
            digest = record.get("sha256")
            if not isinstance(size, int) or size < 0:
                raise BundleError(f"Invalid size for manifest file: {rel}")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise BundleError(f"Invalid SHA-256 for manifest file: {rel}")
            if rel in expected:
                raise BundleError(f"Duplicate manifest file: {rel}")
            expected[rel] = record

        required = set(REQUIRED_FILES)
        missing_required = sorted(required - expected.keys())
        if missing_required:
            raise BundleError("Manifest missing required files: " + ", ".join(missing_required))

        actual_names: set[str] = set()
        checked_bytes = 0
        for info in infos:
            # ZIP symlinks can escape the extraction root on some platforms.
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            if (unix_mode & 0o170000) == 0o120000:
                raise BundleError(f"Symlink entry is not allowed: {info.filename}")
            name = info.filename.replace("\\", "/")
            if name == MANIFEST_PATH or name.endswith("/"):
                continue
            prefix = "flutter_assets/"
            if not name.startswith(prefix):
                raise BundleError(f"Unexpected archive entry: {name}")
            rel = safe_relative_path(name[len(prefix):])
            actual_names.add(rel)
            record = expected.get(rel)
            if record is None:
                raise BundleError(f"File not declared in manifest: {rel}")
            data = archive.read(info)
            checked_bytes += len(data)
            if len(data) != record.get("size_bytes"):
                raise BundleError(f"Size mismatch: {rel}")
            if sha256_bytes(data) != record.get("sha256"):
                raise BundleError(f"SHA-256 mismatch: {rel}")

        if actual_names != expected.keys():
            absent = sorted(expected.keys() - actual_names)
            raise BundleError("Manifest files missing from archive: " + ", ".join(absent[:10]))

        return {
            "valid": True,
            "format_version": FORMAT_VERSION,
            "project_name": manifest.get("project", {}).get("name", "unknown"),
            "file_count": len(actual_names),
            "uncompressed_bytes": checked_bytes,
            "flutter_version": manifest.get("toolchain", {}).get("flutter_version", "unknown"),
            "engine_revision": manifest.get("toolchain", {}).get("engine_revision", "unknown"),
            "manifest": manifest,
        }


def extract_bundle(bundle: Path, destination: Path) -> dict[str, Any]:
    report = verify_bundle(bundle)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle) as archive:
        for info in archive.infolist():
            if info.filename == MANIFEST_PATH:
                continue
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            rel = safe_relative_path(name.removeprefix("flutter_assets/"))
            target = destination / "flutter_assets" / Path(*PurePosixPath(rel).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))
        (destination / "manifest.json").write_bytes(archive.read(MANIFEST_PATH))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Flutter Go bundle tooling (format v1)")
    commands = parser.add_subparsers(dest="command", required=True)

    pack = commands.add_parser("pack", help="Package an extracted flutter_assets directory")
    pack.add_argument("asset_root", type=Path)
    pack.add_argument("output", type=Path)
    pack.add_argument("--name", required=True)
    pack.add_argument("--flutter-version", default="unknown")
    pack.add_argument("--dart-version", default="unknown")
    pack.add_argument("--framework-revision", default="unknown")
    pack.add_argument("--engine-revision", default="unknown")

    verify = commands.add_parser("verify", help="Verify bundle structure, sizes and hashes")
    verify.add_argument("bundle", type=Path)

    extract = commands.add_parser("extract", help="Verify and extract a bundle")
    extract.add_argument("bundle", type=Path)
    extract.add_argument("destination", type=Path)

    args = parser.parse_args()
    try:
        if args.command == "pack":
            manifest = pack_bundle(args.asset_root, args.output, args.name,
                                   args.flutter_version, args.dart_version,
                                   args.framework_revision, args.engine_revision)
            print(f"Created {args.output} ({manifest['totals']['file_count']} files)")
        elif args.command == "verify":
            report = verify_bundle(args.bundle)
            print(json.dumps({k: v for k, v in report.items() if k != "manifest"}, indent=2))
        else:
            report = extract_bundle(args.bundle, args.destination)
            print(f"Extracted {report['file_count']} files to {args.destination}")
        return 0
    except (OSError, zipfile.BadZipFile, BundleError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
