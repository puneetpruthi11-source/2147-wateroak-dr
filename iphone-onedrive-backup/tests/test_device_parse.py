"""Test device output parsing without a real phone (mock the CLI calls)."""

import subprocess

from iphone_backup import device as dev


def _fake_proc(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode,
                                       stdout=stdout, stderr=stderr)


def test_list_connected_udids_json(monkeypatch):
    monkeypatch.setattr(dev, "_run",
                        lambda *a, **k: _fake_proc('["00008030-0011AABB22C0002E"]'))
    assert dev.list_connected_udids() == ["00008030-0011AABB22C0002E"]


def test_list_connected_udids_plain_lines(monkeypatch):
    monkeypatch.setattr(dev, "_run",
                        lambda *a, **k: _fake_proc("00008030-0011AABB22C0002E\n"))
    assert dev.list_connected_udids() == ["00008030-0011AABB22C0002E"]


def test_list_connected_udids_empty(monkeypatch):
    monkeypatch.setattr(dev, "_run", lambda *a, **k: _fake_proc(""))
    assert dev.list_connected_udids() == []


def test_list_media_paths_filters_by_extension(monkeypatch):
    listing = "\n".join([
        "DCIM",
        "DCIM/100APPLE",
        "DCIM/100APPLE/IMG_0001.HEIC",
        "DCIM/100APPLE/IMG_0002.JPG",
        "DCIM/100APPLE/VID_0003.MOV",
        "DCIM/100APPLE/._IMG_0001.HEIC",   # AppleDouble junk -> skip
        "DCIM/100APPLE/notes.txt",          # wrong extension -> skip
        "DCIM/100APPLE/IMG_0004.AAE",       # sidecar -> skip (not in list)
    ])
    monkeypatch.setattr(dev, "_run", lambda *a, **k: _fake_proc(listing))

    exts = [".heic", ".jpg", ".mov"]
    paths = dev.list_media_paths("UDID", "DCIM", exts)
    assert paths == [
        "DCIM/100APPLE/IMG_0001.HEIC",
        "DCIM/100APPLE/IMG_0002.JPG",
        "DCIM/100APPLE/VID_0003.MOV",
    ]


def test_list_media_paths_trust_error(monkeypatch):
    monkeypatch.setattr(dev, "_run",
                        lambda *a, **k: _fake_proc(returncode=1,
                                                   stderr="Device is not paired / trust required"))
    try:
        dev.list_media_paths("UDID", "DCIM", [".heic"])
        assert False, "expected DeviceError"
    except dev.DeviceError as e:
        assert "Trust" in str(e)


def test_check_tools_missing(monkeypatch):
    monkeypatch.setattr(dev.shutil, "which", lambda name: None)
    assert dev.check_tools() == ["pymobiledevice3"]
