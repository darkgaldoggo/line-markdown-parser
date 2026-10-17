"""The publication build must not disclose the local builder's account."""

import importlib.util
import io
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace


def test_sdist_owner_normalization_preserves_payload(tmp_path, monkeypatch):
    # Loading the privacy hook needs no real build environment in the unit suite.
    hooks = SimpleNamespace(
        **{
            name: lambda *args: None
            for name in (
                "build_wheel",
                "build_editable",
                "get_requires_for_build_wheel",
                "get_requires_for_build_sdist",
                "get_requires_for_build_editable",
                "prepare_metadata_for_build_wheel",
                "prepare_metadata_for_build_editable",
            )
        }
    )
    monkeypatch.setitem(sys.modules, "setuptools", SimpleNamespace(build_meta=hooks))
    spec = importlib.util.spec_from_file_location(
        "privacy_build_backend",
        Path(__file__).resolve().parents[1] / "_build_backend.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    archive = tmp_path / "package.tar.gz"
    content = b"public package source\n"
    with tarfile.open(archive, "w:gz") as output:
        member = tarfile.TarInfo("package/source.py")
        member.size = len(content)
        member.uid, member.gid = 501, 20
        member.uname, member.gname = "synthetic-builder", "synthetic-group"
        member.mtime = 123456
        member.pax_headers = {"uname": "synthetic-builder"}
        output.addfile(member, io.BytesIO(content))

    module._normalize_sdist(archive)
    first_build = archive.read_bytes()
    module._normalize_sdist(archive)
    assert archive.read_bytes() == first_build
    with tarfile.open(archive) as result:
        member = result.getmember("package/source.py")
        assert (member.uid, member.gid, member.uname, member.gname, member.mtime) == (
            0,
            0,
            "root",
            "root",
            0,
        )
        assert not member.pax_headers
        assert result.extractfile(member).read() == content
