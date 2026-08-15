"""Exercise the list/dedup/pull/upload loop with the phone and network mocked."""

import shutil
from pathlib import Path

from iphone_backup import backup as backup_mod
from iphone_backup import device as device_mod
from iphone_backup.config import load_config
from iphone_backup.manifest import Manifest


class FakeClient:
    def __init__(self):
        self.uploaded = []

    def upload_file(self, local_path, remote_path):
        # Assert the file really exists at upload time (was pulled).
        assert Path(local_path).is_file(), f"missing {local_path}"
        self.uploaded.append((Path(local_path).name, remote_path))
        return {"id": "fake"}


def _make_phone(tmp_path):
    """A fake on-device DCIM tree living on the local disk."""
    dcim = tmp_path / "phone" / "DCIM" / "100APPLE"
    dcim.mkdir(parents=True)
    (dcim / "IMG_0001.HEIC").write_bytes(b"a" * 10)
    (dcim / "IMG_0002.JPG").write_bytes(b"b" * 20)
    (dcim / "VID_0003.MOV").write_bytes(b"c" * 30)
    return tmp_path / "phone"


def _patch_device(monkeypatch, phone_root, exts):
    """Wire device.list_media_paths/pull_file/device_name to the fake tree."""
    media = ["DCIM/100APPLE/IMG_0001.HEIC",
             "DCIM/100APPLE/IMG_0002.JPG",
             "DCIM/100APPLE/VID_0003.MOV"]

    def fake_list(udid, subdir, include_exts):
        return list(media)

    def fake_pull(udid, remote_path, local_path, timeout=3600):
        src = phone_root / remote_path
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, local_path)

    monkeypatch.setattr(backup_mod.device, "list_media_paths", fake_list)
    monkeypatch.setattr(backup_mod.device, "pull_file", fake_pull)
    monkeypatch.setattr(backup_mod.device, "device_name", lambda udid: "Test iPhone")
    return media


def test_first_pass_uploads_all_media(tmp_path, monkeypatch):
    phone = _make_phone(tmp_path)
    _patch_device(monkeypatch, phone, None)

    cfg = load_config(tmp_path / "state")
    cfg.remote_base_folder = "iPhone Backup"
    client = FakeClient()

    with Manifest(cfg.manifest_path) as manifest:
        result = backup_mod.backup_device(cfg, "UDID", client, manifest)

    assert result.uploaded == 3
    assert result.scanned == 3
    assert result.failed == 0
    assert all(rp.startswith("iPhone Backup/") for _, rp in client.uploaded)


def test_second_pass_skips_already_uploaded(tmp_path, monkeypatch):
    phone = _make_phone(tmp_path)
    _patch_device(monkeypatch, phone, None)
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
    phone = _make_phone(tmp_path)
    media = _patch_device(monkeypatch, phone, None)
    cfg = load_config(tmp_path / "state")

    with Manifest(cfg.manifest_path) as manifest:
        backup_mod.backup_device(cfg, "UDID", FakeClient(), manifest)

    # A newly taken photo appears both on disk and in the device listing.
    (phone / "DCIM" / "100APPLE" / "IMG_0004.HEIC").write_bytes(b"d" * 40)
    media.append("DCIM/100APPLE/IMG_0004.HEIC")

    client = FakeClient()
    with Manifest(cfg.manifest_path) as manifest:
        result = backup_mod.backup_device(cfg, "UDID", client, manifest)

    assert result.uploaded == 1
    assert result.skipped == 3
    assert client.uploaded[0][0] == "IMG_0004.HEIC"


def test_upload_failure_is_recorded_and_loop_continues(tmp_path, monkeypatch):
    phone = _make_phone(tmp_path)
    _patch_device(monkeypatch, phone, None)
    cfg = load_config(tmp_path / "state")

    class FlakyClient(FakeClient):
        def upload_file(self, local_path, remote_path):
            if "IMG_0002" in Path(local_path).name:
                raise RuntimeError("boom")
            return super().upload_file(local_path, remote_path)

    with Manifest(cfg.manifest_path) as manifest:
        result = backup_mod.backup_device(cfg, "UDID", FlakyClient(), manifest)

    assert result.uploaded == 2
    assert result.failed == 1
    assert any("IMG_0002" in e for e in result.errors)

    # A failed file is retried (not skipped) on the next pass.
    with Manifest(cfg.manifest_path) as manifest:
        assert not manifest.has_done("DCIM/100APPLE/IMG_0002.JPG")


def test_disconnect_stops_early_and_keeps_progress(tmp_path, monkeypatch):
    phone = _make_phone(tmp_path)
    media = _patch_device(monkeypatch, phone, None)
    cfg = load_config(tmp_path / "state")

    # Pull works for the first file, then the phone "disconnects".
    real_pull = device_mod.pull_file
    calls = {"n": 0}

    def flaky_pull(udid, remote_path, local_path, timeout=3600):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise device_mod.DeviceError(
                f"Failed to copy {remote_path}: Device not found: 00008130-000915A"
            )
        src = phone / remote_path
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, local_path)

    monkeypatch.setattr(backup_mod.device, "pull_file", flaky_pull)

    client = FakeClient()
    with Manifest(cfg.manifest_path) as manifest:
        result = backup_mod.backup_device(cfg, "UDID", client, manifest)

    assert result.uploaded == 1          # first file made it
    assert result.disconnected is True   # detected the drop
    assert result.failed == 0            # remaining files NOT marked failed — just stopped
    assert "disconnect" in result.summary().lower()

    # On reconnect, the first file is skipped and the rest resume.
    monkeypatch.setattr(backup_mod.device, "pull_file",
                        lambda u, r, l, timeout=3600: shutil.copy2(phone / r, l))
    client2 = FakeClient()
    with Manifest(cfg.manifest_path) as manifest:
        result2 = backup_mod.backup_device(cfg, "UDID", client2, manifest)

    assert result2.skipped == 1
    assert result2.uploaded == 2
