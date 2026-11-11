import json

import pytest

from src.ingest import guard


def sections(tmp_path, version=None):
    p = tmp_path / "sections.jsonl"
    rec = {"lecture_id": "L1"} if version is None else {"lecture_id": "L1", "version": version}
    p.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    return p


def test_the_old_builders_refuse_when_the_live_notes_are_version_2(tmp_path, capsys):
    p = sections(tmp_path, 2)
    assert guard.live_version(p) == 2
    with pytest.raises(SystemExit) as e:
        guard.refuse_v1_overwrite(["prog"], p)
    assert e.value.code == 2 and "scripts/revision_build.py all" in capsys.readouterr().err


def test_force_v1_lets_them_run_and_is_removed_from_the_arguments(tmp_path):
    argv = ["prog", "--force-v1", "--no-extract"]
    guard.refuse_v1_overwrite(argv, sections(tmp_path, 2))
    assert argv == ["prog", "--no-extract"]


def test_first_version_notes_and_missing_files_do_not_block(tmp_path):
    assert guard.live_version(sections(tmp_path)) == 1 and guard.live_version(tmp_path / "none.jsonl") == 0
    guard.refuse_v1_overwrite(["prog"], sections(tmp_path))
    guard.refuse_v1_overwrite(["prog"], tmp_path / "none.jsonl")
