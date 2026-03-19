"""Platform-aware reflink (copy-on-write) file cloning.

Supports two backends:
- Linux: FICLONE ioctl (Btrfs, XFS, etc.)
- macOS: clonefile(2) syscall (APFS)

Both backends raise OSError on failure. Callers should catch OSError and
check ``is_reflink_unsupported(exc)`` to decide whether to fall back to
a plain copy.
"""

import ctypes
import ctypes.util
import errno
import os
import platform
import shutil
from pathlib import Path

# --- errno values that mean "this filesystem doesn't support reflink" -------

REFLINK_UNSUPPORTED_ERRNOS: set[int] = {
    errno.ENOTSUP,
    getattr(errno, 'EOPNOTSUPP', errno.ENOTSUP),
    getattr(errno, 'ENOSYS', errno.ENOTSUP),
    getattr(errno, 'ENOTTY', errno.ENOTSUP),
    getattr(errno, 'EXDEV', errno.ENOTSUP),
}

_SYSTEM = platform.system()

# --- Linux: FICLONE ioctl ---------------------------------------------------

_FICLONE = 0x40049409  # from <linux/fs.h>
_fcntl = None

if _SYSTEM == 'Linux':
    try:
        import fcntl as _fcntl_mod

        _fcntl = _fcntl_mod
    except ImportError:  # pragma: no cover
        pass


def _clone_file_linux(src: Path, dst: Path) -> None:
    """Clone via FICLONE ioctl (Linux only)."""
    assert _fcntl is not None
    with src.open('rb') as src_f, dst.open('wb') as dst_f:
        _fcntl.ioctl(dst_f.fileno(), _FICLONE, src_f.fileno())
    shutil.copystat(src, dst)


# --- macOS: clonefile(2) ----------------------------------------------------

_clonefile_func = None

if _SYSTEM == 'Darwin':
    _libc_path = ctypes.util.find_library('System')
    if _libc_path:
        _libc = ctypes.CDLL(_libc_path, use_errno=True)
        _clonefile_func = _libc.clonefile
        _clonefile_func.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        _clonefile_func.restype = ctypes.c_int


def _clone_file_darwin(src: Path, dst: Path) -> None:
    """Clone via clonefile(2) syscall (macOS only)."""
    assert _clonefile_func is not None
    ret = _clonefile_func(os.fsencode(src), os.fsencode(dst), 0)
    if ret != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err), str(src))
    shutil.copystat(src, dst)


# --- Public API --------------------------------------------------------------


def reflink_supported() -> bool:
    """Return True if the current platform has a reflink backend available."""
    if _SYSTEM == 'Linux':
        return _fcntl is not None
    if _SYSTEM == 'Darwin':
        return _clonefile_func is not None
    return False


def clone_file(src: Path, dst: Path) -> None:
    """Clone a single file using the platform's COW mechanism.

    Raises OSError if the filesystem or platform doesn't support it.
    Use ``is_reflink_unsupported(exc)`` to distinguish "not supported"
    from genuine I/O errors.
    """
    if _SYSTEM == 'Linux' and _fcntl is not None:
        _clone_file_linux(src, dst)
    elif _SYSTEM == 'Darwin' and _clonefile_func is not None:
        _clone_file_darwin(src, dst)
    else:
        raise OSError(errno.ENOTSUP, 'reflink is not supported on this platform')


def is_reflink_unsupported(exc: OSError) -> bool:
    """Return True when the error means reflink isn't available, not a real I/O failure."""
    return exc.errno in REFLINK_UNSUPPORTED_ERRNOS
