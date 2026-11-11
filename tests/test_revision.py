"""Revised-notes import: safe unzip (names, temp files, escapes) and content matching (titles are never used)."""
import zipfile

import pytest

from src.ingest import revision as R


def make_zip(path, names):
    with zipfile.ZipFile(path, "w") as z:
        for n, data in names.items():
            z.writestr(n, data)
    return path


def test_extract_skips_mac_and_temp_files_flattens_and_never_touches_the_zip(tmp_path):
    z = make_zip(tmp_path / "r.zip", {"Revised/Lecture 01.docx": b"a", "__MACOSX/Revised/._Lecture 01.docx": b"x", "Revised/~$Lecture 02.docx": b"t",
                                      "Revised/.DS_Store": b"d", "Revised/Lecture 03.docx": b"c"})
    before = z.read_bytes()
    out = R.extract(z, tmp_path / "out")
    assert [p.name for p in out] == ["Lecture 01.docx", "Lecture 03.docx"] and z.read_bytes() == before
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["Lecture 01.docx", "Lecture 03.docx"]


def test_a_member_that_would_escape_is_flattened_to_its_file_name(tmp_path):
    z = make_zip(tmp_path / "bad.zip", {"../evil.docx": b"x"})
    out = R.extract(z, tmp_path / "out")
    assert [p.parent for p in out] == [(tmp_path / "out").resolve()] and not (tmp_path / "evil.docx").exists()


def test_utf8_names_stored_without_the_flag_are_repaired():
    from types import SimpleNamespace
    shown = "Class 04 \u2013 Laminectomy.pptx".encode("utf-8").decode("cp437")                      # what zipfile shows for UTF-8 bytes without the flag
    assert R.member_name(SimpleNamespace(filename=shown, flag_bits=0)) == "Class 04 \u2013 Laminectomy.pptx"
    assert R.member_name(SimpleNamespace(filename="Class 04 \u2013 Laminectomy.pptx", flag_bits=0x800)) == "Class 04 \u2013 Laminectomy.pptx"


def test_content_matching_ignores_titles_and_pairs_one_to_one():
    old = ["the femoral triangle holds the femoral nerve artery and vein below the inguinal ligament",
           "the carpal tunnel holds the median nerve and the flexor tendons of the hand"]
    new = ["median nerve in the carpal tunnel with flexor tendons of the hand and wrist",
           "femoral nerve artery vein and the inguinal ligament bound the femoral triangle"]
    sim = R.similarity_matrix(old, new)
    assert [(i, j) for i, j, _ in R.assign(sim)] == [(0, 1), (1, 0)]
