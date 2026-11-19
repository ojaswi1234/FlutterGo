from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.bundle_format import BundleError, extract_bundle, pack_bundle, verify_bundle


class BundleFormatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.assets = self.root / "flutter_assets"
        self.assets.mkdir()
        for name, content in {
            "kernel_blob.bin": b"kernel",
            "vm_snapshot_data": b"vm",
            "isolate_snapshot_data": b"isolate",
            "AssetManifest.bin": b"manifest",
            "assets/message.txt": b"hello flutter go",
        }.items():
            path = self.assets / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.bundle = self.root / "sample.fgbundle"

    def tearDown(self):
        self.temp.cleanup()

    def test_pack_verify_extract_roundtrip(self):
        pack_bundle(self.assets, self.bundle, "sample", flutter_version="3.x")
        report = verify_bundle(self.bundle)
        self.assertTrue(report["valid"])
        self.assertEqual(report["file_count"], 5)
        out = self.root / "out"
        extract_bundle(self.bundle, out)
        self.assertEqual((out / "flutter_assets/assets/message.txt").read_bytes(), b"hello flutter go")

    def test_missing_kernel_rejected(self):
        (self.assets / "kernel_blob.bin").unlink()
        with self.assertRaises(BundleError):
            pack_bundle(self.assets, self.bundle, "sample")

    def test_tampered_payload_rejected(self):
        pack_bundle(self.assets, self.bundle, "sample")
        tampered = self.root / "tampered.fgbundle"
        with zipfile.ZipFile(self.bundle) as source, zipfile.ZipFile(tampered, "w") as target:
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename == "flutter_assets/assets/message.txt":
                    data = b"modified"
                target.writestr(info.filename, data)
        with self.assertRaises(BundleError):
            verify_bundle(tampered)

    def test_unsafe_manifest_path_rejected(self):
        pack_bundle(self.assets, self.bundle, "sample")
        unsafe = self.root / "unsafe.fgbundle"
        with zipfile.ZipFile(self.bundle) as source, zipfile.ZipFile(unsafe, "w") as target:
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename == "flutter_go/manifest.json":
                    data = data.replace(b'"kernel_blob.bin"', b'"../kernel_blob.bin"')
                target.writestr(info.filename, data)
        with self.assertRaises(BundleError):
            verify_bundle(unsafe)

    def test_duplicate_archive_entries_rejected(self):
        pack_bundle(self.assets, self.bundle, "sample")
        duplicate = self.root / "duplicate.fgbundle"
        with zipfile.ZipFile(self.bundle) as source, zipfile.ZipFile(duplicate, "w") as target:
            for info in source.infolist():
                target.writestr(info.filename, source.read(info.filename))
            target.writestr("flutter_assets/kernel_blob.bin", b"second copy")
        with self.assertRaises(BundleError):
            verify_bundle(duplicate)

    def test_symlink_entries_rejected(self):
        pack_bundle(self.assets, self.bundle, "sample")
        linked = self.root / "linked.fgbundle"
        with zipfile.ZipFile(self.bundle) as source, zipfile.ZipFile(linked, "w") as target:
            for info in source.infolist():
                target.writestr(info.filename, source.read(info.filename))
            link = zipfile.ZipInfo("flutter_assets/assets/link")
            link.create_system = 3
            link.external_attr = (0o120777 << 16)
            target.writestr(link, b"../../outside")
        with self.assertRaises(BundleError):
            verify_bundle(linked)


if __name__ == "__main__":
    unittest.main()
