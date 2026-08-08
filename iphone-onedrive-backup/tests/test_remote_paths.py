from datetime import datetime

import pytest

from iphone_backup.remote_paths import (
    chunk_ranges,
    encode_graph_path,
    full_remote_path,
    remote_relative_path,
    sanitize_segment,
)


def test_sanitize_removes_illegal_chars():
    assert sanitize_segment('a:b/c*d?.jpg') == 'a_b_c_d?.jpg'.replace('?', '_')


def test_sanitize_strips_trailing_space_and_dot():
    assert sanitize_segment("photo. ") == "photo"
    assert sanitize_segment("...") == "_"


def test_date_layout():
    dt = datetime(2024, 3, 7, 10, 30)
    got = remote_relative_path("100APPLE/IMG_0001.HEIC", dt, "date")
    assert got == "2024/03/IMG_0001.HEIC"


def test_dcim_layout_preserves_structure():
    dt = datetime(2024, 3, 7)
    got = remote_relative_path("100APPLE/IMG_0001.HEIC", dt, "dcim")
    assert got == "100APPLE/IMG_0001.HEIC"


def test_flat_layout_is_filename_only():
    dt = datetime(2024, 3, 7)
    got = remote_relative_path("100APPLE/sub/IMG_0001.HEIC", dt, "flat")
    assert got == "IMG_0001.HEIC"


def test_full_remote_path_joins_base():
    assert full_remote_path("iPhone Backup", "2024/03/IMG.HEIC") == \
        "iPhone Backup/2024/03/IMG.HEIC"


def test_encode_graph_path_keeps_slashes_encodes_spaces():
    enc = encode_graph_path("iPhone Backup/2024/03/IMG 1.HEIC")
    assert enc == "iPhone%20Backup/2024/03/IMG%201.HEIC"


def test_chunk_ranges_exact_multiple():
    ranges = list(chunk_ranges(20, 10))
    assert ranges == [(0, 9, 10), (10, 19, 10)]


def test_chunk_ranges_with_remainder():
    ranges = list(chunk_ranges(25, 10))
    assert ranges == [(0, 9, 10), (10, 19, 10), (20, 24, 5)]
    # ranges are contiguous and cover the whole file
    assert ranges[0][0] == 0
    assert ranges[-1][1] == 24
    assert sum(r[2] for r in ranges) == 25


def test_chunk_ranges_empty_and_invalid():
    assert list(chunk_ranges(0, 10)) == []
    with pytest.raises(ValueError):
        list(chunk_ranges(10, 0))
