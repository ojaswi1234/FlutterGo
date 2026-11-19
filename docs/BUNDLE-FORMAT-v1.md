# Flutter Go bundle format v1

Status: experimental transport format; **not an engine execution contract**.

A `.fgbundle` is a ZIP archive containing:

```text
flutter_go/manifest.json
flutter_assets/kernel_blob.bin
flutter_assets/vm_snapshot_data
flutter_assets/isolate_snapshot_data
flutter_assets/AssetManifest.bin       # if emitted by the Flutter SDK
flutter_assets/<other Flutter assets>
```

The manifest records format version, project name, Flutter/Dart/framework/engine versions, execution mode, native plugin policy, and a SHA-256/size record for every file.

## Validation rules

- Exactly one manifest is required.
- Only format version 1 and debug/JIT artifacts are accepted.
- Kernel, VM snapshot and isolate snapshot files are mandatory for this POC.
- Every payload file must be declared in the manifest and match its size and SHA-256.
- Duplicate ZIP entries, symlinks, path traversal, unexpected top-level files, excessive entry counts and oversized archives are rejected.
- The archive is verified before extraction.

## Security and compatibility notes

SHA-256 detects accidental or malicious modification only when the manifest itself is trusted. It is **not a signature** and does not authenticate the publisher. Do not execute bundles from untrusted sources.

A valid `.fgbundle` only proves transport integrity and required-file presence. It does not prove that a given Flutter engine can load the bundle, resolve its assets, or support its native plugins. The current POC has no runtime loader.
