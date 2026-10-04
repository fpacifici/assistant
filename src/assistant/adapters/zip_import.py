"""Import an uploaded zip of exported HTML notes.

The zip holds one directory per notebook, each `.html` file in it one note —
the layout `HTMLFileImportSource` reads from disk. This module stores the
upload, extracts it safely, runs `run_import` on it and deletes both the zip
and the extracted files afterwards.

Uploads live under `<storage_root>/<user uid>/`:

    <import_id>.zip    uploaded, not imported yet
    <import_id>/       extracted while its import runs

`import_id` is generated here, never taken from a client-supplied path, and
the per-user directory means one user cannot run another user's upload.
"""

from __future__ import annotations

import shutil
import stat
import uuid
import zipfile
import zlib
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, BinaryIO

from assistant.adapters.notes_import import run_import
from assistant.adapters.plugins.html_file import HTMLFileImportSource

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from assistant.adapters.notes_import import ImportReport
    from assistant.models.schema import User

CHUNK_SIZE = 1024 * 1024
DEFAULT_MAX_ENTRIES = 100_000
DEFAULT_MAX_UNCOMPRESSED_BYTES = 10 * 1024 * 1024 * 1024  # 10 GB


class ImportNotFoundError(Exception):
    """No pending upload with this id for this user."""


class UploadTooLargeError(Exception):
    """The upload exceeded the configured size limit."""


class InvalidImportArchiveError(Exception):
    """The upload is not a zip, is unsafe to extract, or holds no notes."""


def store_upload(
    stream: BinaryIO,
    owner: User,
    *,
    storage_root: Path,
    max_bytes: int,
) -> uuid.UUID:
    """Save an uploaded zip for `owner` and return its new import id.

    The file is written under a temporary name and only renamed into place
    once complete and verified, so `import_zip` never sees a partial upload.

    Raises:
        UploadTooLargeError: More than `max_bytes` were sent.
        InvalidImportArchiveError: The upload is not a zip file.
    """
    import_id = uuid.uuid4()
    user_dir = storage_root / str(owner.uid)
    user_dir.mkdir(parents=True, exist_ok=True)
    final_path = user_dir / f"{import_id}.zip"
    partial_path = user_dir / f"{import_id}.zip.part"

    try:
        _write_verified_zip(stream, partial_path, max_bytes=max_bytes)
        partial_path.rename(final_path)
    except BaseException:
        partial_path.unlink(missing_ok=True)
        raise
    return import_id


def _write_verified_zip(stream: BinaryIO, path: Path, *, max_bytes: int) -> None:
    """Copy `stream` to `path` in chunks, enforcing the size limit and zip format."""
    written = 0
    with path.open("wb") as out:
        while chunk := stream.read(CHUNK_SIZE):
            written += len(chunk)
            if written > max_bytes:
                msg = f"Upload exceeds the {max_bytes} byte limit"
                raise UploadTooLargeError(msg)
            out.write(chunk)
    if not zipfile.is_zipfile(path):
        msg = "The uploaded file is not a zip archive"
        raise InvalidImportArchiveError(msg)


def import_zip(  # noqa: PLR0913
    session: Session,
    import_id: uuid.UUID,
    owner: User,
    *,
    storage_root: Path,
    include_web_clips: bool = False,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
) -> ImportReport:
    """Extract and import a stored upload, then delete it whatever happens.

    Raises:
        ImportNotFoundError: `owner` has no pending upload `import_id`.
        InvalidImportArchiveError: The zip is corrupt, unsafe to extract,
            over the limits, or contains no notebook directories with notes.
    """
    user_dir = storage_root / str(owner.uid)
    zip_path = user_dir / f"{import_id}.zip"
    extract_dir = user_dir / str(import_id)
    if not zip_path.is_file():
        raise ImportNotFoundError(str(import_id))

    try:
        _extract(
            zip_path,
            extract_dir,
            max_entries=max_entries,
            max_uncompressed_bytes=max_uncompressed_bytes,
        )
        source = HTMLFileImportSource(
            _notebooks_root(extract_dir),
            include_web_clips=include_web_clips,
        )
        if not source.list_documents():
            msg = (
                "No notes found. The zip should contain one folder per notebook,"
                " with one .html file per note."
            )
            raise InvalidImportArchiveError(msg)
        return run_import(session, source, owner)
    finally:
        zip_path.unlink(missing_ok=True)
        shutil.rmtree(extract_dir, ignore_errors=True)


def _entry_parts(info: zipfile.ZipInfo) -> tuple[str, ...]:
    """Validate an entry's path and return its components.

    Raises:
        InvalidImportArchiveError: Absolute path, drive letter, `..`, or symlink.
    """
    name = info.filename.replace("\\", "/")
    parts = tuple(p for p in PurePosixPath(name).parts if p not in ("", "."))
    if name.startswith("/") or ".." in parts or (parts and ":" in parts[0]):
        msg = f"Unsafe path in zip: {info.filename!r}"
        raise InvalidImportArchiveError(msg)
    if stat.S_ISLNK(info.external_attr >> 16):
        msg = f"Symbolic link in zip: {info.filename!r}"
        raise InvalidImportArchiveError(msg)
    return parts


def _is_ignored(parts: tuple[str, ...]) -> bool:
    """Skip macOS Finder metadata (`__MACOSX/`, `._*`, `.DS_Store`) and dotfiles."""
    return not parts or parts[0] == "__MACOSX" or any(p.startswith(".") for p in parts)


def _extract(
    zip_path: Path,
    dest: Path,
    *,
    max_entries: int,
    max_uncompressed_bytes: int,
) -> None:
    """Extract `zip_path` into `dest`, refusing anything unsafe.

    Sizes are counted from the bytes actually decompressed, not the sizes
    the zip headers claim, so a forged header cannot get past the limit.
    """
    try:
        with zipfile.ZipFile(zip_path) as archive:
            entries = archive.infolist()
            if len(entries) > max_entries:
                msg = f"The zip has more than {max_entries} entries"
                raise InvalidImportArchiveError(msg)
            dest.mkdir(parents=True, exist_ok=True)
            root = dest.resolve()
            total = 0
            for info in entries:
                parts = _entry_parts(info)
                if _is_ignored(parts) or info.is_dir():
                    continue
                target = dest.joinpath(*parts)
                if not target.resolve().is_relative_to(root):
                    msg = f"Unsafe path in zip: {info.filename!r}"
                    raise InvalidImportArchiveError(msg)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, target.open("wb") as out:
                    while chunk := src.read(CHUNK_SIZE):
                        total += len(chunk)
                        if total > max_uncompressed_bytes:
                            msg = (
                                "The zip expands to more than"
                                f" {max_uncompressed_bytes} bytes"
                            )
                            raise InvalidImportArchiveError(msg)
                        out.write(chunk)
    except (zipfile.BadZipFile, zlib.error, EOFError) as exc:
        msg = f"The zip file is corrupt: {exc}"
        raise InvalidImportArchiveError(msg) from exc
    except (RuntimeError, NotImplementedError) as exc:
        # zipfile raises these for encrypted entries and unsupported compression.
        msg = f"The zip file cannot be read: {exc}"
        raise InvalidImportArchiveError(msg) from exc


def _notebooks_root(extract_dir: Path) -> Path:
    """The directory whose subdirectories are notebooks.

    A zip made by compressing a folder (e.g. macOS Finder's "Compress")
    wraps everything in that one folder. If the only top-level entry is a
    directory with no `.html` files of its own, it is such a wrapper and its
    contents are the notebooks. A single top-level directory that does hold
    `.html` files is a notebook itself.
    """
    children = list(extract_dir.iterdir())
    if len(children) == 1 and children[0].is_dir():
        only = children[0]
        if not any(only.glob("*.html")):
            return only
    return extract_dir
