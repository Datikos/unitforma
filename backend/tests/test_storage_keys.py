"""Storage keys for long file names (ADR-0016 #F6): every path component of a key stays under
the 255-byte filesystem limit of the local backend, deterministic and distinct."""

from __future__ import annotations

import uuid

from unitforma.storage.service import MAX_KEY_PART_BYTES, LocalStorage, object_key, safe_filename

T, P = uuid.UUID(int=1), uuid.UUID(int=2)
LONG = (
    "საპროექტო ტერიტორიის გენერალური გეგმა, მასშტაბი 1:500 "
    "შენობა-ნაგებობის ყველა სართულისა და სახურავის გეგმები.pdf"
)


def test_short_names_keep_their_key():
    assert object_key(T, P, "documents", "abc", "plans rev C.pdf") == (
        f"t/{T}/p/{P}/documents/abc/plans%20rev%20C.pdf"
    )


def test_long_georgian_name_is_cut_with_a_hash_and_its_extension():
    name = safe_filename(LONG)
    key = object_key(T, P, "documents", "abc", name)
    last = key.rsplit("/", 1)[1]
    assert len(last.encode()) <= MAX_KEY_PART_BYTES < 255
    assert last.endswith(".pdf") and "-" in last
    assert key == object_key(T, P, "documents", "abc", name)  # deterministic
    other = object_key(T, P, "documents", "abc", name.replace("გეგმები", "ჭრილები"))
    assert other != key  # same leading letters, different names → different keys
    # never cut inside a %XX escape: the component decodes
    from urllib.parse import unquote

    assert unquote(last).encode("utf-8").decode("utf-8")


def test_the_local_backend_stores_a_long_name(tmp_path):
    s = LocalStorage(tmp_path, "secret-for-tests-only")
    key = object_key(T, P, "documents", "abc", safe_filename(LONG))
    s.put_bytes(key, b"%PDF-1.4", "application/pdf")
    assert s.get_bytes(key) == b"%PDF-1.4"
