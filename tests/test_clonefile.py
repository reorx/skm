"""Tests for skm.clonefile — platform-aware reflink/COW cloning."""

import errno
import platform
import shutil

import pytest

from skm import clonefile
from skm.clonefile import (
    clone_file,
    is_reflink_unsupported,
    reflink_supported,
)

_SYSTEM = platform.system()


# --- is_reflink_unsupported --------------------------------------------------


def test_is_reflink_unsupported_recognises_enotsup():
    assert is_reflink_unsupported(OSError(errno.ENOTSUP, 'not supported'))


def test_is_reflink_unsupported_rejects_eio():
    assert not is_reflink_unsupported(OSError(errno.EIO, 'disk error'))


# --- reflink_supported -------------------------------------------------------


def test_reflink_supported_returns_bool():
    result = reflink_supported()
    assert isinstance(result, bool)
    if _SYSTEM == 'Darwin':
        # macOS with APFS should have clonefile available
        assert result is True
    elif _SYSTEM == 'Linux':
        # Linux should have fcntl available
        assert result is True


def test_reflink_supported_false_on_unknown_platform(monkeypatch):
    monkeypatch.setattr(clonefile, '_SYSTEM', 'FreeBSD')
    assert reflink_supported() is False


# --- clone_file: unsupported platform ----------------------------------------


def test_clone_file_raises_on_unsupported_platform(monkeypatch, tmp_path):
    monkeypatch.setattr(clonefile, '_SYSTEM', 'FreeBSD')
    src = tmp_path / 'src.txt'
    dst = tmp_path / 'dst.txt'
    src.write_text('hello')
    with pytest.raises(OSError) as exc_info:
        clone_file(src, dst)
    assert is_reflink_unsupported(exc_info.value)


# --- clone_file: Linux backend via monkeypatch --------------------------------


def test_clone_file_linux_delegates_to_ficlone_ioctl(monkeypatch, tmp_path):
    """Verify the Linux path calls fcntl.ioctl with FICLONE."""
    calls = []

    class FakeFcntl:
        @staticmethod
        def ioctl(dst_fd, request, src_fd):
            calls.append((dst_fd, request, src_fd))

    monkeypatch.setattr(clonefile, '_SYSTEM', 'Linux')
    monkeypatch.setattr(clonefile, '_fcntl', FakeFcntl)

    src = tmp_path / 'src.txt'
    dst = tmp_path / 'dst.txt'
    src.write_text('hello')

    clone_file(src, dst)

    assert len(calls) == 1
    _dst_fd, request, _src_fd = calls[0]
    assert request == 0x40049409  # _FICLONE


# --- clone_file: macOS backend via monkeypatch --------------------------------


def test_clone_file_darwin_delegates_to_clonefile_syscall(monkeypatch, tmp_path):
    """Verify the macOS path calls the clonefile C function."""
    calls = []

    def fake_clonefile(src_bytes, dst_bytes, flags):
        calls.append((src_bytes, dst_bytes, flags))
        # Simulate success by actually copying
        shutil.copy2(src_bytes.decode(), dst_bytes.decode())
        return 0

    monkeypatch.setattr(clonefile, '_SYSTEM', 'Darwin')
    monkeypatch.setattr(clonefile, '_clonefile_func', fake_clonefile)

    src = tmp_path / 'src.txt'
    dst = tmp_path / 'dst.txt'
    src.write_text('hello')

    clone_file(src, dst)

    assert len(calls) == 1
    assert calls[0][2] == 0  # flags


def test_clone_file_darwin_raises_on_failure(monkeypatch, tmp_path):
    """Verify macOS clonefile errors are raised as OSError."""
    import ctypes

    def fake_clonefile(src_bytes, dst_bytes, flags):
        ctypes.set_errno(errno.ENOTSUP)
        return -1

    monkeypatch.setattr(clonefile, '_SYSTEM', 'Darwin')
    monkeypatch.setattr(clonefile, '_clonefile_func', fake_clonefile)

    src = tmp_path / 'src.txt'
    dst = tmp_path / 'dst.txt'
    src.write_text('hello')

    with pytest.raises(OSError) as exc_info:
        clone_file(src, dst)
    assert is_reflink_unsupported(exc_info.value)


# --- Real clone_file on current platform -------------------------------------


@pytest.mark.skipif(not reflink_supported(), reason='reflink not available on this platform')
def test_clone_file_real(tmp_path):
    """Attempt a real reflink clone on the current filesystem.

    On APFS (macOS) this should succeed and produce a COW clone.
    On Linux this depends on the filesystem (Btrfs/XFS succeed, ext4 fails).
    If the filesystem doesn't support it, the error should be recognised
    by is_reflink_unsupported.
    """
    src = tmp_path / 'original.txt'
    src.write_text('content for reflink test')
    dst = tmp_path / 'cloned.txt'

    try:
        clone_file(src, dst)
    except OSError as exc:
        # Filesystem doesn't support reflink — that's OK, just verify
        # we correctly identify it as "unsupported" rather than a real error.
        assert is_reflink_unsupported(exc), f'unexpected OSError: {exc}'
        return

    assert dst.read_text() == 'content for reflink test'
    # On a COW filesystem, inodes should differ (it's a clone, not a hardlink)
    assert src.stat().st_ino != dst.stat().st_ino


@pytest.mark.skipif(not reflink_supported(), reason='reflink not available on this platform')
def test_clone_file_real_dst_must_not_exist(tmp_path):
    """clonefile(2) on macOS refuses to overwrite; FICLONE on Linux creates dst via open('wb')."""
    src = tmp_path / 'src.txt'
    src.write_text('hello')
    dst = tmp_path / 'dst.txt'
    dst.write_text('already here')

    if _SYSTEM == 'Darwin':
        # macOS clonefile fails with EEXIST
        with pytest.raises(OSError):
            clone_file(src, dst)
    else:
        # Linux FICLONE opens dst with 'wb' (truncates), so this succeeds
        clone_file(src, dst)
        assert dst.read_text() == 'hello'
