# Flutter Go — Runtime Research POC

This repository is a **research harness**, not a working Expo Go replacement. It prepares and inspects the exact Flutter Android debug bundle that a future custom host would need to load.

## Current objective

Validate the Android debug artifact contract before implementing a custom engine/asset provider:

1. Build the included sample Flutter app as a debug APK.
2. Inspect the APK's `assets/flutter_assets` contents.
3. Record the Kernel, VM/isolate snapshots, asset manifest, and project assets.
4. Use the generated report as the input specification for the native-host experiment.

## Requirements

- Flutter SDK compatible with the sample project.
- Android SDK and an Android device/emulator for the later native-host experiment.
- Python 3.10+ for the bundle inspector and tests.

The development machine should have Flutter, Android SDK/ADB, Java, and Python available. `flutter-go doctor` reports tool availability separately from whether a physical Android device or emulator is connected.

## Run the sample

From `sample_flutter_project/` (the repository intentionally keeps generated Android/Gradle files out of source control):

```bash
flutter create --platforms=android .
flutter pub get
flutter build apk --debug
```

Then, from this repository root:

```bash
python tools/inspect_flutter_bundle.py \
  inspect sample_flutter_project/build/app/outputs/flutter-apk/app-debug.apk \
  --output build/inspected-sample
```

The command writes:

- `build/inspected-sample/flutter_assets/` — extracted Flutter assets
- `build/inspected-sample/bundle-report.json` — paths, sizes, SHA-256 hashes, and validation results

If your Flutter version emits the APK at a different path, pass that path instead.

## Flutter Go CLI (experimental bundle format v1)

The CLI can inspect, package, verify and extract debug bundles. It is a transport tool only; it does not execute bundles in an Android host.

Check local prerequisites and whether ADB sees a device:

```powershell
py -m tools.flutter_go doctor
```

Build, inspect, package, and verify in one command (recommended):

```powershell
py -m tools.flutter_go capture sample_flutter_project --output build/capture --name sample-runtime
```

The command creates Android platform scaffolding if missing, runs `flutter pub get`, builds a debug APK, extracts `flutter_assets`, records an inspection report, packages `sample-runtime.fgbundle`, and verifies the result. It does not install or execute the bundle on a device.

The steps are also available individually. To inspect an existing APK:

```powershell
py -m tools.flutter_go inspect-apk sample_flutter_project/build/app/outputs/flutter-apk/app-debug.apk --output build/inspected-sample
```

Then package and verify:

```powershell
py -m tools.flutter_go pack build/inspected-sample/flutter_assets build/runtime-probe.fgbundle --name runtime-probe
py -m tools.flutter_go verify build/runtime-probe.fgbundle
py -m tools.flutter_go extract build/runtime-probe.fgbundle build/unpacked
```

See [`docs/BUNDLE-FORMAT-v1.md`](docs/BUNDLE-FORMAT-v1.md) for the format and its security limitations.

## Run tests

```bash
python -m unittest discover -s tests -v
```

## What this POC does not prove

The inspector only confirms what is packaged in a conventional debug APK. It does **not** prove that a separate Android host can execute another project's Kernel or resolve its assets. That requires a native experiment using a JIT-capable engine and an external asset provider/container.

See `docs/ADR-001-runtime-loading.md` for the current architecture decision and `docs/POC-01-test-plan.md` for the next device experiment.
