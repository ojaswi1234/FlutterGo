import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.inspect_flutter_bundle import inspect, safe_asset_name


class BundleInspectorTests(unittest.TestCase):
    def make_apk(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in {
                "assets/flutter_assets/kernel_blob.bin": b"kernel",
                "assets/flutter_assets/vm_snapshot_data": b"vm",
                "assets/flutter_assets/isolate_snapshot_data": b"isolate",
                "assets/flutter_assets/AssetManifest.bin": b"manifest",
                "assets/flutter_assets/assets/message.txt": b"hello",
            }.items():
                archive.writestr(name, data)

    def test_inspects_and_extracts_debug_apk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            apk = root / "sample.apk"
            output = root / "out"
            self.make_apk(apk)
            report = inspect(apk, output)
            self.assertEqual(report["validation"], "pass")
            self.assertEqual(report["asset_count"], 5)
            self.assertTrue((output / "flutter_assets/assets/message.txt").is_file())
            self.assertTrue((output / "bundle-report.json").is_file())
            self.assertEqual(report["asset_manifests_found"], ["AssetManifest.bin"])

    def test_rejects_missing_kernel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            apk = root / "bad.apk"
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr("assets/flutter_assets/AssetManifest.json", b"{}")
            with self.assertRaises(FileNotFoundError):
                inspect(apk, root / "out")

    def test_safe_asset_name_rejects_traversal(self):
        self.assertIsNone(safe_asset_name("flutter_assets/../../secret"))
        self.assertIsNone(safe_asset_name("/flutter_assets/kernel_blob.bin"))
        self.assertEqual(
            safe_asset_name("flutter_assets/images/logo.png"),
            "flutter_assets/images/logo.png",
        )


if __name__ == "__main__":
    unittest.main()
