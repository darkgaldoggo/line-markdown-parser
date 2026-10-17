"""Setuptools build hooks with anonymous source-archive ownership metadata."""

from __future__ import annotations

import gzip
import os
import stat
import tarfile
import tempfile
from pathlib import Path

from setuptools import build_meta as _backend

build_wheel = _backend.build_wheel
build_editable = _backend.build_editable
get_requires_for_build_wheel = _backend.get_requires_for_build_wheel
get_requires_for_build_sdist = _backend.get_requires_for_build_sdist
get_requires_for_build_editable = _backend.get_requires_for_build_editable
prepare_metadata_for_build_wheel = _backend.prepare_metadata_for_build_wheel
prepare_metadata_for_build_editable = _backend.prepare_metadata_for_build_editable


def _normalize_sdist(path: Path) -> None:
    """Remove builder account names, numeric IDs, and local archive timestamps."""
    mode = stat.S_IMODE(path.stat().st_mode)
    descriptor, temporary = tempfile.mkstemp(suffix=".tar.gz", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=output, mtime=0
            ) as compressed:
                with (
                    tarfile.open(path, "r:gz") as source,
                    tarfile.open(
                        fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT
                    ) as target,
                ):
                    for member in source.getmembers():
                        payload = (
                            source.extractfile(member) if member.isfile() else None
                        )
                        member.uid = member.gid = 0
                        member.uname = member.gname = "root"
                        member.mtime = 0
                        member.pax_headers = {}
                        target.addfile(member, payload)
                        if payload is not None:
                            payload.close()
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def build_sdist(sdist_directory, config_settings=None):
    name = _backend.build_sdist(sdist_directory, config_settings)
    _normalize_sdist(Path(sdist_directory) / name)
    return name
