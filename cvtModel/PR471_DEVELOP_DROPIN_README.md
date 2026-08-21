# PR #471 / develop semantic-merge drop-in

Extract this archive at the repository root so its `cvtModel/` directory overlays
the existing `cvtModel/` directory. Do **not** delete the existing directory first:
this archive intentionally contains only the files that need replacement/addition,
so unrelated newer `develop` content (including the Ballew study) is preserved.

After extraction, the hill-step sanity command is:

```powershell
& C:\Python312\python.exe .\cvtModel\launchTools\run_hill_step_response.py
```

See `cvtModel/docs/PR471_DEVELOP_MERGE_NOTES.md` for what was merged and the
validation performed.
