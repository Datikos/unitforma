"""LocalStorage raises one clear error on an unwritable root (a root-owned Docker volume)."""

import os
import stat

import pytest

from unitforma.storage.service import LocalStorage


@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="directory modes do not restrict root or Windows",
)
def test_unwritable_root_raises_clear_error(tmp_path):
    root = tmp_path / "storage"
    root.mkdir()
    root.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(PermissionError, match="not writable"):
            LocalStorage(root, "secret")
    finally:
        root.chmod(stat.S_IRWXU)


def test_writable_root_round_trips(tmp_path):
    s = LocalStorage(tmp_path / "storage", "secret")
    s.put_bytes("t/1/p/2/a.txt", b"hi", "text/plain")
    assert s.get_bytes("t/1/p/2/a.txt") == b"hi"
