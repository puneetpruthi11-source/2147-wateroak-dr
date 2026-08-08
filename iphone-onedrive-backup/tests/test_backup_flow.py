"""Exercise the scan/dedup/upload loop with the phone and network mocked out."""

from contextlib import contextmanager

from iphone_backup import backup as backup_mod
from iphone_backup import device as device_mod
from iphone_backup.config import load_config
from iphone_backup.manifest import Manifest


class FakeClient:
    def __init__(self):
        self.uploaded = []

    def upload_file(self, local_path, remote_path):
        self.uploaded.append((str(local_path), remote_path))
        return {"id": "fake"}


def _make_dcim(tmp_path):
    dcim = tmp_path / "phone" / "DCIM" / "100APPLE"
    dcim.mkdir(parents=True)
    (dcim / "IMG_0001.HEIC").write_bytes(b"a" * 10)
    (dcim / "IMG_0002.JPG").write_bytes(b"b" * 20)
    (dcim / "VID_0003.MOV").write_bytes(b"c" * 30)
    (dcim / "._IMG_0001.HEIC").write_bytes(b"junk")   # AppleDouble, must skip
    (dcim / "notes.txt").write_bytes(b"nope")          # wrong extension, skip
    return tmp_path / "phone"


def _patch(monkeypatch, mount_root):
    @contextmanager
    def fake_mount(udid, mount_point):
        yield mount_root

    monkeypatch.setattr(device_mod, "mounted_media", fake_mount)
    monkeypatch.setattr(backup_mod.device, "mounted_media", fake_mount)
    monkeypatch.setattr(backup_mod.device, "device_name", lambda udid: "Test iPhone")


def test_first_pass_uploads_media_only(tmp_path, monkeypatch):
    mount_root = _make_dcim(tmp_path)
    _patch(monkeypatch, mount_root)

    cfg = load_config(tmp_path / "state")
    cfg.remote_base_folder = "iPhone Backup"
    client = FakeClient()

    with Manifest(cfg.manifest_path) as manifest:
        result = backup_mod.backup_device(cfg, "UDID", client, manifest)

    assert result.uploaded == 3          # 3 media files
    assert result.scanned == 3           # junk + txt excluded from scan entirely
    assert result.failed == 0
    remote_paths = sorted(rp for _, rp in client.uploaded)
    assert all(p.startswith("iPhone Backup/") for p in remote_paths)


def test_second_pass_skips_already_uploaded(tmp_path, monkeypatch):
    mount_root = _make_dcim(tmp_path)
    _patch(monkeypatch, mount_root)

    cfg = load_config(tmp_path / "state")

    with Manifest(cfg.manifest_path) as manifest:
        backup_mod.backup_device(cfg, "UDID", FakeClient(), manifest)

    client2 = FakeClient()
    with Manifest(cfg.manifest_path) as manifest:
        result = backup_mod.backup_device(cfg, "UDID", client2, manifest)

    assert result.uploaded == 0
    assert result.skipped == 3
    assert client2.uploaded == []


def test_new_photo_after_first_pass_is_picked_up(tmp_path, monkeypatch):
    mount_root = _make_dcim(tmp_path)
    _patch(monkeypatch, mount_root)
    cfg = load_config(tmp_path / "state")

    with Manifest(cfg.manifest_path) as manifest:
        backup_mod.backup_device(cfg, "UDID", FakeClient(), manifest)

    # Simulate a newly taken photo.
    (mount_root / "DCIM" / "100APPLE" / "IMG_0004.HEIC").write_bytes(b"d" * 40)

    client = FakeClient()
    with Manifest(cfg.manifest_path) as manifest:
        result = backup_mod.backup_device(cfg, "UDID", client, manifest)

    assert result.uploaded == 1
    assert result.skipped == 3
    assert client.uploaded[0][0].endswith("IMG_0004.HEIC")


def test_upload_failure_is_recorded_and_loop_continues(tmp_path, monkeypatch):
    mount_root = _make_dcim(tmp_path)
    _patch(monkeypatch, mount_root)
    cfg = load_config(tmp_path / "state")

    class FlakyClient(FakeClient):
        def upload_file(self, local_path, remote_path):
            if "IMG_0002" in str(local_path):
                raise RuntimeError("boom")
            return super().upload_file(local_path, remote_path)

    with Manifest(cfg.manifest_path) as manifest:
        result = backup_mod.backup_device(cfg, "UDID", FlakyClient(), manifest)

    assert result.uploaded == 2
    assert result.failed == 1
    assert any("IMG_0002" in e for e in result.errors)
