"""Accounts: salted scrypt hashes, roles, grants, lockout, first-run seeding."""
import json

import pytest

from src import auth


@pytest.fixture(autouse=True)
def users_file(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "USERS_PATH", tmp_path / "users.json")
    monkeypatch.setattr(auth, "_fails", {})
    return tmp_path / "users.json"


def test_seed_creates_one_professor_and_two_students_with_no_grants(users_file, monkeypatch):
    monkeypatch.setenv("DEMO_PROFESSOR_PASSWORD", "prof-pass-1")
    monkeypatch.setenv("DEMO_STUDENT_PASSWORD", "stud-pass-1")
    said = []
    assert auth.ensure_seed(said.append) is True
    users = auth.load_users()
    assert sorted(users) == ["inglis", "student1", "student2"]
    assert [u["role"] for u in users.values()].count("professor") == 1
    assert all(users[s]["allowed_lectures"] == [] for s in ("student1", "student2"))
    assert auth.ensure_seed(said.append) is False and len(said) == 1          # seeds (and announces) only once
    assert "prof-pass-1" not in said[0] and "DEMO_PROFESSOR_PASSWORD" in said[0]  # an env password is never echoed


def test_generated_password_is_shown_once_and_works(users_file, monkeypatch):
    monkeypatch.delenv("DEMO_PROFESSOR_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_STUDENT_PASSWORD", raising=False)
    said = []
    auth.ensure_seed(said.append)
    pw = next(l for l in said[0].splitlines() if "inglis" in l).split("password:")[1].strip()
    assert auth.authenticate("inglis", pw)["role"] == "professor"


def test_passwords_are_never_stored_in_plain_text(users_file):
    auth.save_users({"p": auth.new_record("P", "professor", "correct horse battery")})
    raw = users_file.read_text()
    assert "correct horse" not in raw
    rec = json.loads(raw)["p"]
    assert len(rec["salt"]) == 32 and len(rec["hash"]) == 64 and set(rec) >= {"salt", "hash", "role", "name"}
    assert oct(users_file.stat().st_mode & 0o777) == "0o600"


def test_same_password_gets_a_different_salt_and_hash():
    a, b = auth.new_record("a", "student", "same-password"), auth.new_record("b", "student", "same-password")
    assert a["salt"] != b["salt"] and a["hash"] != b["hash"]


def test_authenticate_accepts_the_right_password_only(users_file):
    auth.save_users({"s": auth.new_record("S", "student", "right-password", ["Lecture 09 - The Hand"])})
    user = auth.authenticate("s", "right-password")
    assert user == {"username": "s", "name": "S", "role": "student", "allowed_lectures": ["Lecture 09 - The Hand"]}
    assert "hash" not in user and "salt" not in user
    assert auth.authenticate("s", "wrong-password") is None
    assert auth.authenticate("nobody", "right-password") is None
    assert auth.authenticate("s", "") is None


def test_lockout_after_five_failures_then_expires(users_file):
    auth.save_users({"s": auth.new_record("S", "student", "right-password")})
    for _ in range(5):
        assert auth.authenticate("s", "bad", now=1000.0) is None
    assert auth.locked("s", now=1001.0)
    assert auth.authenticate("s", "right-password", now=1001.0) is None        # locked even with the right password
    assert not auth.locked("s", now=1000.0 + auth.LOCK_SECONDS + 1)
    assert auth.authenticate("s", "right-password", now=1000.0 + auth.LOCK_SECONDS + 1)


def test_only_students_get_grants_and_they_apply_at_once(users_file):
    auth.save_users({"p": auth.new_record("P", "professor", "prof-password"), "s": auth.new_record("S", "student", "stud-password")})
    auth.set_allowed_lectures("s", ["B", "A", "A"])
    assert auth.get_user("s")["allowed_lectures"] == ["A", "B"]
    with pytest.raises(ValueError):
        auth.set_allowed_lectures("p", ["A"])
    with pytest.raises(ValueError):
        auth.set_allowed_lectures("ghost", ["A"])


def test_new_students_start_with_no_access_and_weak_passwords_are_refused(users_file):
    auth.save_users({})
    auth.add_student("newbie", "New B", "long-enough-pw")
    assert auth.get_user("newbie")["allowed_lectures"] == [] and auth.get_user("newbie")["role"] == "student"
    with pytest.raises(ValueError):
        auth.add_student("short", "S", "abc")
    with pytest.raises(ValueError):
        auth.add_student("newbie", "dup", "long-enough-pw")
    with pytest.raises(ValueError):
        auth.add_student("bad name!", "x", "long-enough-pw")


def test_password_reset(users_file):
    auth.save_users({"s": auth.new_record("S", "student", "old-password")})
    auth.set_password("s", "new-password-1")
    assert auth.authenticate("s", "old-password") is None and auth.authenticate("s", "new-password-1")
