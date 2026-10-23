"""Release guards reject a wrong tag or a different artifact under an existing filename."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "check_release", Path(__file__).resolve().parents[2] / "scripts/check_release.py"
)
assert spec and spec.loader
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_candidate_tag_must_match_both_packages():
    version = release.release_version()
    release.validate_tag(f"v{version}", version)
    with pytest.raises(ValueError, match="Release must use tag"):
        release.validate_tag("main", version)
    with pytest.raises(ValueError, match="Release must use tag"):
        release.validate_tag("v999.0.0", version)


def test_existing_and_published_files_are_content_checked(tmp_path):
    wheel = tmp_path / "package.whl"
    wheel.write_bytes(b"candidate")
    remote = {
        "urls": [
            {
                "filename": wheel.name,
                "digests": {"sha256": hashlib.sha256(b"candidate").hexdigest()},
            }
        ]
    }
    release.verify_files([wheel], remote, required=True)
    release.verify_files([wheel], {"urls": []}, required=False)
    with pytest.raises(ValueError, match="missing"):
        release.verify_files([wheel], {"urls": []}, required=True)
    wheel.write_bytes(b"different")
    with pytest.raises(ValueError, match="differs"):
        release.verify_files([wheel], remote, required=False)
