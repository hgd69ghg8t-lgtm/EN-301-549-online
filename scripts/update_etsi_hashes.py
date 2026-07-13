#!/usr/bin/env python3
"""Refreshes data/etsi-content-hashes.json, the wording-integrity baseline
for every protected clause/annex content/*.html file (see
validate_etsi_content_integrity() in scripts/build.py).

This is a deliberate, maintainer-run action — scripts/build.py never runs
it automatically, because the whole point of the check is that the
baseline can only change when a person consciously decides the current
wording is correct and re-baselines it. Re-run this:
  - once, to establish the initial baseline;
  - after a genuine transcription-error correction against the source PDF
    (explain what you fixed and why in your commit message);
  - after adding a new clause/annex content file.

Never run this just to make a validation failure go away without first
checking *why* the wording changed — that defeats the whole point of the
check.

Usage: python3 scripts/update_etsi_hashes.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402


def main():
    protected = build.protected_etsi_slugs()
    hashes = {}
    for slug in protected:
        fragment_path = build.CONTENT_DIR / f"{slug}.html"
        if not fragment_path.exists():
            print(f"Skipping {slug}: content/{slug}.html does not exist.", file=sys.stderr)
            continue
        hashes[slug] = build.etsi_content_hash(fragment_path.read_text(encoding="utf-8"))
    build.ETSI_HASHES_PATH.write_text(
        json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(hashes)} wording-integrity hashes to {build.ETSI_HASHES_PATH}")


if __name__ == "__main__":
    main()
