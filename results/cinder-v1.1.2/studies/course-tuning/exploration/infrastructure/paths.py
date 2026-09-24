"""Locate archived campaigns without changing paths recorded in original evidence."""
from pathlib import Path
from .common import STUDY_ROOT


def saved_campaign_path(recorded: str, anchor: Path) -> Path:
    path = Path(recorded)
    if (path/'campaign.json').is_file():
        return path
    normalized = str(recorded).replace('\\', '/')
    if '/artifacts/' not in normalized:
        return path
    suffix = normalized.split('/artifacts/', 1)[1]
    if '..' in Path(suffix).parts or Path(suffix).is_absolute():
        raise ValueError('Unsafe archived campaign path')
    # A relocated feature plan and its campaigns retain their shared artifact root.
    for parent in (Path(anchor).resolve().parent, *Path(anchor).resolve().parents):
        candidate = parent/suffix
        if (candidate/'campaign.json').is_file():
            return candidate
        if parent == STUDY_ROOT:
            break
    root = STUDY_ROOT/'artifacts'
    candidates = [root/suffix, *(p/suffix for p in sorted(root.glob('imported_*')))]
    for candidate in candidates:
        if (candidate/'campaign.json').is_file():
            return candidate
    return path
