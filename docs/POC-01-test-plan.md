# POC-01: Android external-bundle experiment

## Phase A — artifact inventory (this repository implements this phase)

- [x] Include a minimal Flutter sample project.
- [x] Inspect a debug APK's `assets/flutter_assets` directory.
- [x] Report required debug runtime files, asset manifest variants, file sizes, and hashes.
- [ ] Run `flutter-go capture` against an APK built with the target Flutter SDK.

## Phase B — host and runtime experiment (requires Android SDK/device)

1. Record exact Flutter framework revision and engine revision from `flutter --version --machine`.
2. Build and install a minimal JIT/debug-capable Android host. Do not use an AOT-only release engine for the first test.
3. Verify the host can start its own ordinary Flutter entrypoint.
4. Build the sample app independently and extract its debug `flutter_assets` tree.
5. Test the stock embedding path with a separately constructed `AssetManager`/asset container. Do not use reflection or hidden APIs in a product design; if a prototype requires them, record that as a blocker/risk.
6. If the stock asset-container route fails, create a minimal engine patch implementing a directory-backed asset provider and document the patch surface.
7. Start the sample project's Kernel and confirm its UI renders.
8. Load the sample text asset, then add a PNG and a custom font to test asset lookup variants.
9. Destroy the preview engine and relaunch it.
10. Only after launch works, test VM service discovery, DDS, `flutter attach`, and hot reload.

## Required measurements

- Host APK size.
- External bundle size.
- Cold start time (5 runs; report median and range).
- Preview engine memory delta (host idle vs one preview vs two previews).
- Asset lookup success/failure.
- Crash/logcat output.
- Exact SDK/engine revision.

## Pass/fail gates

**Gate 1 — code loading:** separately compiled sample project renders without installing its own APK.

**Gate 2 — assets:** app assets resolve correctly from the external bundle.

**Gate 3 — lifecycle:** repeated start/stop does not leak or crash.

**Gate 4 — development loop:** Flutter attach/hot reload works without rebuilding the host.

Do not proceed to multi-preview or polished companion UI before Gates 1 and 2 pass.

## Phase A implementation update (2026-11-19)

- [x] Implement experimental `.fgbundle` format v1 with a versioned JSON manifest.
- [x] Record toolchain versions/revisions and per-file SHA-256/size metadata.
- [x] Verify archive structure and payload integrity before extraction.
- [x] Reject duplicate entries, symlinks, traversal paths, undeclared files and oversized archives.
- [x] Add CLI commands: `doctor`, `capture`, `inspect-apk`, `pack`, `verify`, `extract`.
- [x] Report connected ADB devices separately from installed Android build prerequisites.
- [x] Add round-trip, tampering, missing-file, traversal, duplicate-entry and symlink tests.
- [ ] Validate using an APK produced by the target Flutter SDK. The ChatGPT execution environment has no Flutter SDK/ADB; the user has confirmed Flutter 3.47.9, Android SDK 36, JDK 21 and ADB are installed on their Windows machine.

The test suite currently passes 9 tests. A separate CLI smoke test passed using a synthetic asset tree. This validates packaging and verification code only; it is not a real Flutter APK or Android runtime test.
