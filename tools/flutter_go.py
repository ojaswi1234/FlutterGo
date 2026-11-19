#!/usr/bin/env python3
"""Flutter Go developer CLI: inspect, package, verify and extract POC bundles."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from tools.bundle_format import BundleError, extract_bundle, pack_bundle, verify_bundle
from tools.inspect_flutter_bundle import inspect as inspect_apk


def flutter_metadata() -> dict[str, str]:
    executable = shutil.which("flutter")
    if not executable:
        raise RuntimeError("Flutter SDK not found on PATH")
    result = subprocess.run(
        [executable, "--version", "--machine"],
        check=True, capture_output=True, text=True, timeout=30,
    )
    data = json.loads(result.stdout)
    return {
        "flutter_version": str(data.get("frameworkVersion", "unknown")),
        "dart_version": str(data.get("dartSdkVersion", "unknown")),
        "framework_revision": str(data.get("frameworkRevision", "unknown")),
        "engine_revision": str(data.get("engineRevision", "unknown")),
        "channel": str(data.get("channel", "unknown")),
    }


def connected_android_devices() -> list[dict[str, str]]:
    adb = shutil.which("adb")
    if not adb:
        return []
    result = subprocess.run([adb, "devices", "-l"], check=True, capture_output=True,
                            text=True, timeout=15)
    devices = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append({"serial": parts[0], "details": " ".join(parts[2:])})
    return devices


def run_flutter(project: Path, *arguments: str) -> None:
    executable = shutil.which("flutter")
    if not executable:
        raise RuntimeError("Flutter SDK not found on PATH")
    print("$ flutter " + " ".join(arguments), flush=True)
    subprocess.run([executable, *arguments], cwd=project, check=True, timeout=1800)


def capture_project(project: Path, output: Path, name: str) -> dict:
    project = project.resolve()
    if not (project / "pubspec.yaml").is_file():
        raise RuntimeError(f"Not a Flutter project (pubspec.yaml missing): {project}")
    if not (project / "android").is_dir():
        run_flutter(project, "create", "--platforms=android", ".")
    run_flutter(project, "pub", "get")
    run_flutter(project, "build", "apk", "--debug")

    apk = project / "build" / "app" / "outputs" / "flutter-apk" / "app-debug.apk"
    if not apk.is_file():
        raise RuntimeError(f"Flutter build completed but expected APK was not found: {apk}")
    inspected = inspect_apk(apk, output)
    if inspected["validation"] != "pass":
        raise RuntimeError("Built APK is missing required JIT/debug runtime files; see bundle-report.json")
    metadata = flutter_metadata()
    bundle = output / f"{name}.fgbundle"
    manifest = pack_bundle(
        output / "flutter_assets", bundle, name,
        metadata["flutter_version"], metadata["dart_version"],
        metadata["framework_revision"], metadata["engine_revision"],
    )
    verification = verify_bundle(bundle)
    return {
        "apk": str(apk),
        "inspection_report": str(output / "bundle-report.json"),
        "bundle": str(bundle),
        "file_count": manifest["totals"]["file_count"],
        "uncompressed_bytes": manifest["totals"]["uncompressed_bytes"],
        "flutter_version": metadata["flutter_version"],
        "engine_revision": metadata["engine_revision"],
        "verified": verification["valid"],
    }


def doctor() -> dict:
    tools = {}
    for name in ("flutter", "dart", "adb", "java"):
        path = shutil.which(name)
        tools[name] = {"available": path is not None, "path": path}
    if tools["flutter"]["available"]:
        try:
            tools["flutter"]["metadata"] = flutter_metadata()
        except Exception as exc:  # diagnostic should report, not crash
            tools["flutter"]["metadata_error"] = str(exc)
    devices = []
    device_error = None
    if tools["adb"]["available"]:
        try:
            devices = connected_android_devices()
        except (OSError, subprocess.SubprocessError) as exc:
            device_error = str(exc)
    prerequisites = all(tools[name]["available"] for name in ("flutter", "adb", "java"))
    return {
        "tools": tools,
        "android_devices": devices,
        "android_device_error": device_error,
        "ready_for_bundle_packaging": True,
        "ready_for_android_runtime_test": prerequisites,
        "android_device_connected": bool(devices),
        "note": "Runtime prerequisites are installed. Connect an Android device with USB debugging enabled or start an emulator before device testing.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="flutter-go", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Check local development prerequisites and Android devices")

    capture = sub.add_parser("capture", help="Build a Flutter debug APK and package its runtime assets")
    capture.add_argument("project", type=Path, help="Flutter project directory containing pubspec.yaml")
    capture.add_argument("--output", type=Path, default=Path("build/capture"))
    capture.add_argument("--name", default="flutter-go-capture")

    inspect_cmd = sub.add_parser("inspect-apk", help="Extract and inspect flutter_assets from a debug APK")
    inspect_cmd.add_argument("apk", type=Path)
    inspect_cmd.add_argument("--output", type=Path, required=True)

    pack = sub.add_parser("pack", help="Create a .fgbundle from an extracted flutter_assets directory")
    pack.add_argument("asset_root", type=Path)
    pack.add_argument("output", type=Path)
    pack.add_argument("--name", required=True)
    pack.add_argument("--flutter-version")
    pack.add_argument("--dart-version")
    pack.add_argument("--framework-revision")
    pack.add_argument("--engine-revision")

    verify = sub.add_parser("verify", help="Verify a .fgbundle")
    verify.add_argument("bundle", type=Path)

    extract = sub.add_parser("extract", help="Verify and extract a .fgbundle")
    extract.add_argument("bundle", type=Path)
    extract.add_argument("destination", type=Path)

    args = parser.parse_args()
    try:
        if args.command == "doctor":
            print(json.dumps(doctor(), indent=2))
        elif args.command == "capture":
            result = capture_project(args.project, args.output, args.name)
            print(json.dumps(result, indent=2))
        elif args.command == "inspect-apk":
            report = inspect_apk(args.apk, args.output)
            print(json.dumps({k: v for k, v in report.items() if k != "files"}, indent=2))
            if report["validation"] != "pass":
                return 1
        elif args.command == "pack":
            metadata = {}
            if any(value is None for value in (args.flutter_version, args.dart_version,
                                                args.framework_revision, args.engine_revision)):
                try:
                    metadata = flutter_metadata()
                except Exception:
                    metadata = {}
            manifest = pack_bundle(
                args.asset_root, args.output, args.name,
                args.flutter_version or metadata.get("flutter_version", "unknown"),
                args.dart_version or metadata.get("dart_version", "unknown"),
                args.framework_revision or metadata.get("framework_revision", "unknown"),
                args.engine_revision or metadata.get("engine_revision", "unknown"),
            )
            print(json.dumps({"output": str(args.output), **manifest["totals"]}, indent=2))
        elif args.command == "verify":
            report = verify_bundle(args.bundle)
            print(json.dumps({k: v for k, v in report.items() if k != "manifest"}, indent=2))
        else:
            report = extract_bundle(args.bundle, args.destination)
            print(json.dumps({"destination": str(args.destination), **{k: v for k, v in report.items() if k != "manifest"}}, indent=2))
        return 0
    except (OSError, RuntimeError, ValueError, BundleError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
