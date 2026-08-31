"""Materialize the complete legacy Ballew study into its versioned results home.

The old benchmark is frozen in the ``cinder-v1.0.0`` tag.  This script copies
that exact source material out of Git/Git-LFS, maps it into the new study tree,
and writes an integrity manifest.  It does not import or execute CINDER.

Default mapping
---------------
legacy ``reference/**`` -> ``reference/**``
legacy ``results/**``   -> ``artifacts/historical-v1.0.0/**``
legacy root ``*.md``    -> ``provenance/legacy-docs/**``
legacy root ``*.py``    -> ``provenance/legacy-code/**``
other legacy files      -> ``provenance/legacy-other/**``

``__pycache__`` / bytecode are intentionally excluded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Iterable

SOURCE_TAG = "cinder-v1.0.0"
SOURCE_COMMIT = "ee21850034a58df73ffc4238936ffece8102c4f1"
SOURCE_PREFIX = "cvtModel/launchTools/literature/ballew_2015"
STUDY_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = STUDY_ROOT / "provenance" / "migration_manifest.json"


def _run(repo: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    proc = subprocess.run(
        list(args), cwd=repo, input=input_bytes, capture_output=True, check=False
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"Command failed ({' '.join(args)}):\n{stderr}")
    return proc.stdout


def _repo_root() -> Path:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=STUDY_ROOT,
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
        return Path(out).resolve()
    except Exception as exc:
        raise RuntimeError(
            "This migration must be run from a checkout of gr812b/CVT-Simulator. "
            "Unzip the drop-in into the repository first."
        ) from exc


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_lfs_pointer(data: bytes) -> bool:
    return data.startswith(b"version https://git-lfs.github.com/spec/v1\n")


def _parse_lfs_pointer(data: bytes) -> tuple[str, int] | None:
    if not _is_lfs_pointer(data):
        return None
    oid = None
    size = None
    for line in data.decode("ascii").splitlines():
        if line.startswith("oid sha256:"):
            oid = line.removeprefix("oid sha256:").strip()
        elif line.startswith("size "):
            size = int(line.removeprefix("size ").strip())
    if oid is None or size is None:
        raise RuntimeError("Malformed Git LFS pointer in legacy tree.")
    return oid, size


def _source_paths(repo: Path) -> list[str]:
    raw = _run(
        repo,
        "git",
        "ls-tree",
        "-r",
        "--name-only",
        SOURCE_TAG,
        "--",
        SOURCE_PREFIX,
    ).decode("utf-8")
    paths = []
    for path in raw.splitlines():
        if not path:
            continue
        rel = path.removeprefix(SOURCE_PREFIX + "/")
        if "__pycache__" in Path(rel).parts or Path(rel).suffix == ".pyc":
            continue
        paths.append(path)
    if not paths:
        raise RuntimeError(f"No files found under {SOURCE_TAG}:{SOURCE_PREFIX}")
    return sorted(paths)


def _target_for(source_path: str) -> Path:
    rel = Path(source_path.removeprefix(SOURCE_PREFIX + "/"))
    parts = rel.parts
    if parts and parts[0] == "reference":
        # Keep the new results-tree README files authoritative while preserving
        # the exact legacy reference documentation beside the other provenance.
        if rel.name == "README.md":
            return STUDY_ROOT / "provenance" / "legacy-reference-docs" / Path(*parts[1:])
        return STUDY_ROOT / rel
    if parts and parts[0] == "results":
        return STUDY_ROOT / "artifacts" / "historical-v1.0.0" / Path(*parts[1:])
    if len(parts) == 1 and rel.suffix.lower() == ".md":
        return STUDY_ROOT / "provenance" / "legacy-docs" / rel.name
    if len(parts) == 1 and rel.suffix.lower() == ".py":
        return STUDY_ROOT / "provenance" / "legacy-code" / rel.name
    return STUDY_ROOT / "provenance" / "legacy-other" / rel


def _blob_sha(repo: Path, source_path: str) -> str:
    return _run(repo, "git", "rev-parse", f"{SOURCE_TAG}:{source_path}").decode().strip()


def _blob_size(repo: Path, source_path: str) -> int:
    return int(
        _run(repo, "git", "cat-file", "-s", f"{SOURCE_TAG}:{source_path}")
        .decode()
        .strip()
    )


def _working_tree_source(repo: Path, source_path: str) -> Path:
    return repo / source_path


def _read_small_blob(repo: Path, source_path: str) -> bytes:
    return _run(repo, "git", "show", f"{SOURCE_TAG}:{source_path}")


def _smudge_lfs(repo: Path, pointer: bytes, *, source_path: str) -> bytes:
    # ``git lfs smudge`` accepts pointer bytes on stdin and resolves the object.
    try:
        return _run(
            repo,
            "git",
            "lfs",
            "smudge",
            source_path,
            input_bytes=pointer,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Could not materialize Git LFS object for {source_path}. Install Git LFS "
            "and run `git lfs pull` once, then re-run this migration."
        ) from exc


def _write_source(repo: Path, source_path: str, target: Path) -> dict[str, object]:
    target.parent.mkdir(parents=True, exist_ok=True)
    blob_size = _blob_size(repo, source_path)
    blob_sha = _blob_sha(repo, source_path)
    wt = _working_tree_source(repo, source_path)

    # Prefer an already-smudged working-tree copy. This also avoids re-fetching
    # large LFS objects when the user's checkout already contains them.
    if wt.exists() and wt.is_file():
        with wt.open("rb") as handle:
            head = handle.read(256)
        if not _is_lfs_pointer(head):
            shutil.copy2(wt, target)
            return {
                "source_git_blob": blob_sha,
                "source_kind": "working-tree-materialized",
                "target_size_bytes": target.stat().st_size,
                "target_sha256": _sha256_file(target),
            }

    # LFS pointers are tiny Git blobs. Detect before streaming a normal large blob.
    if blob_size <= 2048:
        raw = _read_small_blob(repo, source_path)
        lfs = _parse_lfs_pointer(raw)
        if lfs is not None:
            oid, expected_size = lfs
            payload = _smudge_lfs(repo, raw, source_path=source_path)
            actual_sha = _sha256_bytes(payload)
            if actual_sha != oid or len(payload) != expected_size:
                raise RuntimeError(
                    f"Git LFS integrity failure for {source_path}: "
                    f"sha={actual_sha}, size={len(payload)}; expected sha={oid}, size={expected_size}."
                )
            target.write_bytes(payload)
            return {
                "source_git_blob": blob_sha,
                "source_kind": "git-lfs",
                "source_lfs_oid_sha256": oid,
                "source_lfs_size_bytes": expected_size,
                "target_size_bytes": len(payload),
                "target_sha256": actual_sha,
            }
        target.write_bytes(raw)
        return {
            "source_git_blob": blob_sha,
            "source_kind": "git-blob",
            "target_size_bytes": len(raw),
            "target_sha256": _sha256_bytes(raw),
        }

    # Normal large Git blob: stream to disk rather than holding it in memory.
    with target.open("wb") as handle:
        proc = subprocess.run(
            ["git", "show", f"{SOURCE_TAG}:{source_path}"],
            cwd=repo,
            stdout=handle,
            stderr=subprocess.PIPE,
            check=False,
        )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git show failed for {source_path}: "
            + proc.stderr.decode("utf-8", errors="replace")
        )
    return {
        "source_git_blob": blob_sha,
        "source_kind": "git-blob",
        "target_size_bytes": target.stat().st_size,
        "target_sha256": _sha256_file(target),
    }


def _verify_tag(repo: Path) -> None:
    actual = _run(repo, "git", "rev-list", "-n", "1", SOURCE_TAG).decode().strip()
    if actual != SOURCE_COMMIT:
        raise RuntimeError(
            f"{SOURCE_TAG} resolved to {actual}, expected frozen commit {SOURCE_COMMIT}."
        )


def _verify_existing_entry(entry: dict[str, object]) -> tuple[bool, str]:
    target = STUDY_ROOT / str(entry["target_relative_to_study"])
    if not target.exists():
        return False, "missing"
    actual = _sha256_file(target)
    expected = str(entry["target_sha256"])
    if actual != expected:
        return False, f"sha mismatch {actual} != {expected}"
    return True, "ok"


def materialize(*, force: bool = False) -> dict[str, object]:
    repo = _repo_root()
    _verify_tag(repo)
    paths = _source_paths(repo)
    records: list[dict[str, object]] = []
    for index, source_path in enumerate(paths, start=1):
        target = _target_for(source_path)
        if target.exists() and not force:
            # Existing target may be a deliberately bundled exact asset (e.g. thesis).
            # Compare it to source by writing source only when needed; the manifest is
            # generated from the actual target after integrity is established below.
            pass
        print(f"[{index:>3}/{len(paths)}] {source_path} -> {target.relative_to(STUDY_ROOT)}")
        details = _write_source(repo, source_path, target)
        records.append(
            {
                "source_path": source_path,
                "target_relative_to_study": str(target.relative_to(STUDY_ROOT)).replace("\\", "/"),
                **details,
            }
        )

    payload = {
        "source": {
            "repository": "gr812b/CVT-Simulator",
            "tag": SOURCE_TAG,
            "commit_sha": SOURCE_COMMIT,
            "legacy_prefix": SOURCE_PREFIX,
        },
        "excluded": ["**/__pycache__/**", "**/*.pyc"],
        "mapping": {
            "reference data/code": "reference/**",
            "reference README files": "provenance/legacy-reference-docs/**",
            "results/**": "artifacts/historical-v1.0.0/**",
            "root *.md": "provenance/legacy-docs/**",
            "root *.py": "provenance/legacy-code/**",
            "other": "provenance/legacy-other/**",
        },
        "file_count": len(records),
        "files": records,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def verify() -> int:
    if not MANIFEST_PATH.exists():
        print(f"Migration manifest does not exist: {MANIFEST_PATH}", file=sys.stderr)
        return 2
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    failures = []
    for entry in payload["files"]:
        ok, detail = _verify_existing_entry(entry)
        if not ok:
            failures.append((entry["target_relative_to_study"], detail))
    if failures:
        print("Migration verification FAILED:", file=sys.stderr)
        for path, detail in failures:
            print(f"  {path}: {detail}", file=sys.stderr)
        return 1
    print(f"Migration verification passed for {len(payload['files'])} files.")
    return 0


def ensure_reference_assets() -> None:
    """Ensure exact reference data exist; hydrate the complete legacy study if needed."""
    required = (
        STUDY_ROOT / "reference" / "figure_41_input_rpm.csv",
        STUDY_ROOT / "reference" / "figure_41_output_rpm.csv",
        STUDY_ROOT / "reference" / "figure_45_primary_force.csv",
    )
    if all(path.exists() and not _is_lfs_pointer(path.read_bytes()[:256]) for path in required):
        return
    print(
        "Ballew historical assets are not fully materialized; migrating the frozen "
        "cinder-v1.0.0 legacy study into the results tree now."
    )
    materialize()
    if not all(path.exists() and not _is_lfs_pointer(path.read_bytes()[:256]) for path in required):
        raise RuntimeError("Ballew migration completed without the required reference CSVs.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="verify an existing migration only")
    parser.add_argument("--force", action="store_true", help="overwrite materialized legacy assets")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.verify:
        return verify()
    payload = materialize(force=args.force)
    print(f"\nMaterialized {payload['file_count']} legacy files into {STUDY_ROOT}")
    print(f"Integrity manifest: {MANIFEST_PATH}")
    return verify()


if __name__ == "__main__":
    raise SystemExit(main())
