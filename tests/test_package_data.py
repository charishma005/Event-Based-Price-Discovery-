import hashlib
import zipfile

import pytest

from scripts.package_steps_1_5_8_data import pack, sha256_of


def _files(tmp_path):
    first, second = tmp_path / "a.bin", tmp_path / "b.bin"
    first.write_bytes(b"alpha")
    second.write_bytes(b"beta")
    return first, second


def test_pack_adds_only_what_the_archive_does_not_hold_yet(tmp_path):
    first, second = _files(tmp_path)
    archive = tmp_path / "out.zip"
    expected = {"raw/a.bin": hashlib.sha256(b"alpha").hexdigest()}
    assert pack(archive, [("raw/a.bin", first)], expected) == 0
    assert pack(archive, [("raw/a.bin", first), ("raw/b.bin", second)], expected) == 0
    with zipfile.ZipFile(archive) as stored:
        assert stored.namelist() == ["raw/a.bin", "raw/b.bin"]
        assert stored.read("raw/b.bin") == b"beta"
        assert all(item.compress_type == zipfile.ZIP_STORED for item in stored.infolist())


def test_pack_stops_at_the_time_budget_and_resumes(tmp_path):
    first, second = _files(tmp_path)
    archive = tmp_path / "out.zip"
    entries = [("raw/a.bin", first), ("raw/b.bin", second)]
    assert pack(archive, entries, {}, max_seconds=1e-9) == 2
    assert pack(archive, entries, {}) == 0
    with zipfile.ZipFile(archive) as stored:
        assert stored.testzip() is None and len(stored.namelist()) == 2


def test_pack_refuses_a_file_that_does_not_match_its_recorded_hash(tmp_path):
    first, _ = _files(tmp_path)
    archive = tmp_path / "out.zip"
    with pytest.raises(SystemExit):
        pack(archive, [("raw/a.bin", first)], {"raw/a.bin": "0" * 64})
    with zipfile.ZipFile(archive) as stored:
        assert stored.namelist() == []


def test_sha256_of_reads_the_whole_file(tmp_path):
    first, _ = _files(tmp_path)
    assert sha256_of(first) == hashlib.sha256(b"alpha").hexdigest()


def test_check_against_list_reports_missing_and_changed_files(tmp_path, monkeypatch):
    import pandas as pd

    import scripts.package_steps_1_5_8_data as package

    first, second = _files(tmp_path)
    monkeypatch.setattr(package, "raw_databento_dirs", lambda: [tmp_path])
    listed = pd.DataFrame({
        "file": ["a.bin", "b.bin", "c.bin"],
        "bytes": [5, 4, 1],
        "sha256": [hashlib.sha256(b"alpha").hexdigest(), hashlib.sha256(b"BETA").hexdigest(), "0" * 64],
    })
    missing, different = package.check_against_list(listed)
    assert missing == ["c.bin"]
    assert different == ["b.bin"]
