from iphone_backup.manifest import Manifest


def test_new_file_is_not_uploaded(tmp_path):
    with Manifest(tmp_path / "m.db") as m:
        assert not m.is_uploaded("IMG_0001.HEIC", 100, 111)


def test_mark_done_then_is_uploaded(tmp_path):
    with Manifest(tmp_path / "m.db") as m:
        m.mark_done("IMG_0001.HEIC", 100, 111, "iPhone Backup/2024/03/IMG_0001.HEIC")
        assert m.is_uploaded("IMG_0001.HEIC", 100, 111)


def test_changed_size_or_mtime_reuploads(tmp_path):
    with Manifest(tmp_path / "m.db") as m:
        m.mark_done("IMG.HEIC", 100, 111, "r")
        assert not m.is_uploaded("IMG.HEIC", 200, 111)  # size changed
        assert not m.is_uploaded("IMG.HEIC", 100, 222)  # mtime changed


def test_failed_is_not_treated_as_uploaded(tmp_path):
    with Manifest(tmp_path / "m.db") as m:
        m.mark_failed("IMG.HEIC", 100, 111, "network error")
        assert not m.is_uploaded("IMG.HEIC", 100, 111)
        counts = m.counts()
        assert counts["failed"] == 1
        assert counts["done"] == 0


def test_failed_then_done_updates_status(tmp_path):
    with Manifest(tmp_path / "m.db") as m:
        m.mark_failed("IMG.HEIC", 100, 111, "err")
        m.mark_done("IMG.HEIC", 100, 111, "r")
        assert m.is_uploaded("IMG.HEIC", 100, 111)
        counts = m.counts()
        assert counts["failed"] == 0
        assert counts["done"] == 1


def test_counts_and_clear(tmp_path):
    with Manifest(tmp_path / "m.db") as m:
        m.mark_done("a", 1, 1, "r")
        m.mark_done("b", 1, 1, "r")
        assert m.counts()["done"] == 2
        m.clear()
        assert m.counts()["done"] == 0


def test_persists_across_reopen(tmp_path):
    db = tmp_path / "m.db"
    with Manifest(db) as m:
        m.mark_done("a", 5, 9, "r")
    with Manifest(db) as m:
        assert m.is_uploaded("a", 5, 9)
