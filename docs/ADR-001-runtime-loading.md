# ADR-001: External Flutter project loading on Android

- Status: **Provisional — standard embedding path rejected for arbitrary external bundles**
- Date: 2026-11-19

## Context

Flutter Go's differentiating goal is to preview independently built Flutter projects inside one installed Android companion app.

A normal Android Flutter application packages its debug runtime data and app code under the host APK's Flutter assets. The question is whether the stock Android embedding provides a supported public path to load a different project's Kernel and assets at runtime.

## Findings

### 1. VM initialization is process-level

`FlutterJNI.init()` initializes the Dart VM and Flutter engine once. The stock `FlutterLoader` derives the JIT Kernel path from its own extracted app-data `flutter_assets` directory and passes that path into `FlutterJNI.init()`.

References:
- https://api.flutter.dev/javadoc/io/flutter/embedding/engine/FlutterJNI.html
- https://chromium.googlesource.com/external/github.com/flutter/flutter/+/156c44315fbf682db427b307a67d5e3768932000/engine/src/flutter/shell/platform/android/io/flutter/embedding/engine/loader/FlutterLoader.java

### 2. Per-engine launch path is asset-provider based

`FlutterJNI.runBundleAndSnapshotFromLibrary()` accepts a bundle path plus an Android `AssetManager`. The Android native implementation constructs an `APKAssetProvider` from that manager and path, then launches the shell with that provider.

The `bundlePath` in this method is therefore an asset-bundle directory, not a free-standing path to an arbitrary `.dill`/Kernel file.

References:
- https://api.flutter.dev/javadoc/io/flutter/embedding/engine/FlutterJNI.html
- https://github.com/flutter-team-archive/engine/blob/main/shell/platform/android/platform_view_android_jni_impl.cc

The engine repository above is archived. Treat its implementation as source-level evidence for that code snapshot, not a guarantee that every future engine revision is identical. Re-check the exact engine source corresponding to the selected Flutter SDK before implementation.

### 3. Flutter debug artifact layout

Flutter's Android debug bundle target copies `app.dill` to `flutter_assets/kernel_blob.bin`, and also packages `vm_snapshot_data`, `isolate_snapshot_data`, and project assets/manifests.

Reference:
- https://github.com/flutter/flutter/blob/master/packages/flutter_tools/lib/src/build_system/targets/common.dart

### 4. Multiple engines are not the blocker

Flutter supports multiple `FlutterEngine` instances in one Android process. They share the Dart VM but run separate isolates. This does not by itself provide independent bundle loading.

Reference:
- https://api.flutter.dev/javadoc/io/flutter/embedding/engine/FlutterEngine.html

## Decision

Do not implement the full companion UI or assume `FlutterEngineGroup` solves arbitrary project loading.

Keep three runtime paths under evaluation:

1. **Custom engine/asset provider:** modify or extend the Android embedding/native engine so each preview can resolve a separate project bundle from a controlled directory or archive.
2. **Android asset-container approach:** determine whether a project archive can be exposed through a supported Android `AssetManager`/split-asset mechanism without hidden APIs or engine changes. This must be tested; do not assume an ordinary ZIP is sufficient.
3. **Generated project host:** build a project-specific host when native dependencies or stock embedding constraints require it. This is the compatibility fallback, not the target UX.

## Consequences

- The stock public embedding API is not yet sufficient evidence for a universal shared runtime.
- The first practical work item is to inspect and test the real debug bundle structure.
- A JIT-capable runtime must be considered separately from the normal AOT release Flutter app. A release-mode AOT host cannot simply be assumed to execute arbitrary debug Kernel bundles.
- Native plugins remain host-build-time capabilities unless a different, supported mechanism is proven.
- No runtime security boundary should be inferred from Dart isolates.

## Exit criteria for changing this ADR

Change the status only after a device test demonstrates all of the following:

- A host APK installed once can launch a separately built sample project's Kernel.
- The project can load its own image/font/file assets.
- The host does not need to be rebuilt for a second project with the same declared compatibility contract.
- Failure modes for incompatible engine/framework versions are detected cleanly.

## Implementation update: transport format v1

An experimental `.fgbundle` transport format and Python CLI have been added. The format carries a JSON manifest and the extracted `flutter_assets` tree, with per-file SHA-256 and size checks. The verifier rejects path traversal, symlink entries, duplicate ZIP entries, undeclared files and archive size/count limits.

This does not change the runtime decision. A valid `.fgbundle` is not proof that Flutter's Android engine can execute it. The format is explicitly marked experimental and debug/JIT-only. Its manifest hashes are integrity checks, not publisher authentication or a signature.


## Implementation update — target toolchain confirmed

The target Windows development environment reports Flutter 3.47.9 stable, Dart 3.13.7, framework revision `c197ca5199e9ee5661e865596c9c07294dfab51c`, engine revision `89c39edfdfae2949f6806e4a315c0c08522238b7`, Android SDK 36.0.0 and JDK 21. The Android build prerequisites are present. Flutter Doctor currently lists no connected Android device or emulator, so APK generation can proceed but on-device runtime validation must wait for a target.
