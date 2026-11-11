"""The first-version builders (src.ingest.parse, scripts/guides_build.py) read the FIRST files and would overwrite the live revised (version 2) notes, guides and map.
They refuse unless --force-v1 is passed, and print how to rebuild version 2 instead."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V2_HELP = ("The live notes and guides are version 2 (the revised ones). This builder reads the FIRST files and would overwrite them with version 1.\n"
           "To rebuild version 2:   .venv/bin/python scripts/revision_build.py all     (builds data/staging_v2/)\n"
           "                        REVISION_STAGE=data/staging_v2 .venv/bin/python -m pytest -q tests     (check it)\n"
           "                        .venv/bin/python scripts/revision_swap.py swap     (backs up, then swaps it in)\n"
           "To really rebuild version 1 (a backup of version 1 is in data/archive/), run this command again with --force-v1.")


def live_version(sections_path=None):
    """1 or 2: the `version` of the first record of the live sections.jsonl (records without one are version 1). 0 when there is no file."""
    p = Path(sections_path or ROOT / "data" / "processed" / "sections.jsonl")
    if not p.exists():
        return 0
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                return int(json.loads(line).get("version", 1))
    return 0


def refuse_v1_overwrite(argv=None, sections_path=None):
    """Call first in an old builder's main(). Exits with the v2 command unless --force-v1 is in argv. Removes the flag so the builder's own parser never sees it."""
    argv = sys.argv if argv is None else argv
    if "--force-v1" in argv:
        argv.remove("--force-v1")
        return
    if live_version(sections_path) >= 2:
        print(V2_HELP, file=sys.stderr)
        raise SystemExit(2)
