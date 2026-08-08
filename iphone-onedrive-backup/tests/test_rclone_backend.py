from iphone_backup.rclone_backend import build_copyto_args


def test_copyto_args_basic():
    args = build_copyto_args("onedrive", "iPhone Backup/2024/03/IMG.HEIC", "/mnt/IMG.HEIC")
    assert args[:2] == ["rclone", "copyto"]
    # source then destination, destination is remote:path
    assert args[-2] == "/mnt/IMG.HEIC"
    assert args[-1] == "onedrive:iPhone Backup/2024/03/IMG.HEIC"


def test_copyto_args_with_config_and_extra():
    args = build_copyto_args(
        "od", "a/b.jpg", "/x/b.jpg",
        config_path="/home/me/rclone.conf",
        extra_args=["--onedrive-chunk-size", "10M"],
    )
    assert "--config" in args
    assert args[args.index("--config") + 1] == "/home/me/rclone.conf"
    assert "--onedrive-chunk-size" in args
    assert args[-1] == "od:a/b.jpg"


def test_spaces_are_single_argv_elements():
    # Passed as a list, so spaces never need shell-escaping.
    args = build_copyto_args("onedrive", "My Photos/a b.jpg", "/tmp/a b.jpg")
    assert "onedrive:My Photos/a b.jpg" in args
    assert "/tmp/a b.jpg" in args
