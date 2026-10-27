"""Demo-grade accounts: roles (professor, student), salted scrypt password hashes, per-student lecture grants.

NOT production security. Accounts live in one local file (data/users.json, git-ignored) and the web app trusts the
Python process it runs in. A real deployment needs UB single sign-on. What this does do properly:
  * passwords are never stored: only a random salt and an scrypt hash (hashlib.scrypt), compared in constant time;
  * a student's lecture grants are read from the file on every request, so a change by the professor applies at once;
  * the grants are enforced in the search layer (Searcher.search(allowed_lectures=...)), not only in the UI.

First run: seeds one professor and two sample students. The professor's password comes from DEMO_PROFESSOR_PASSWORD, or a
random one is generated and printed ONCE to the terminal that started the app (it is not written anywhere else). Sample
students use DEMO_STUDENT_PASSWORD or a generated password, printed once in the same way. Sample students start with
access to no lectures.
"""
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USERS_PATH = Path(os.environ.get("ANATOVISION_USERS_PATH") or ROOT / "data" / "users.json")
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}
MIN_PASSWORD = 10
PASSWORD_RULES = (f"At least {MIN_PASSWORD} characters.", "Not the same as the username.",
                  "Not only spaces. Type it twice to confirm.")
ROLES = ("professor", "student")
MAX_FAILS, LOCK_SECONDS = 5, 300
_fails = {}          # username -> [timestamps of recent failures] (in memory: demo-grade throttling)


def demo_mode():
    """The 'demo login, not production security' notice is shown only while ANATOVISION_DEMO is on (default: on)."""
    return os.environ.get("ANATOVISION_DEMO", "1").strip().lower() not in ("0", "false", "no", "off")


def check_password_rules(password, confirm=None, username=""):
    """Raise ValueError with a clear message if the password breaks a rule. The message never contains the password."""
    if password is None or not password.strip():
        raise ValueError("Type a password.")
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"The password is too short: it needs at least {MIN_PASSWORD} characters "
                         f"(you typed {len(password)}).")
    if username and password.strip().lower() == username.strip().lower():
        raise ValueError("The password must not be the same as the username.")
    if confirm is not None and password != confirm:
        raise ValueError("The two passwords do not match. Type the same password in both boxes.")


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, **SCRYPT)
    return salt.hex(), digest.hex()


def check_password(password, salt_hex, hash_hex):
    digest = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex), **SCRYPT)
    return hmac.compare_digest(digest.hex(), hash_hex)


def load_users():
    try:
        return json.loads(Path(USERS_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_users(users):
    path = Path(USERS_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(users, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def new_record(name, role, password, allowed_lectures=()):
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    check_password_rules(password)
    salt, digest = hash_password(password)
    return {"name": name, "role": role, "salt": salt, "hash": digest,
            "allowed_lectures": [] if role == "professor" else sorted(set(allowed_lectures))}


def public(username, record):
    """The record without the salt and hash: the only form that goes to the UI."""
    return {"username": username, "name": record["name"], "role": record["role"],
            "allowed_lectures": list(record.get("allowed_lectures", []))}


def get_user(username):
    record = load_users().get(username)
    return public(username, record) if record else None


def _say(text):
    print(text, flush=True)


def ensure_seed(announce=_say):
    """Create the first accounts if data/users.json does not exist. Returns True if it seeded."""
    if Path(USERS_PATH).exists():
        return False
    given_prof, given_stud = os.environ.get("DEMO_PROFESSOR_PASSWORD"), os.environ.get("DEMO_STUDENT_PASSWORD")
    for var, given in (("DEMO_PROFESSOR_PASSWORD", given_prof), ("DEMO_STUDENT_PASSWORD", given_stud)):
        if given:
            try:
                check_password_rules(given)
            except ValueError as exc:                 # name the variable, never echo its value
                raise ValueError(f"{var} is not usable: {exc}") from None
    prof_pw = given_prof or secrets.token_urlsafe(9)
    stud_pw = given_stud or secrets.token_urlsafe(9)
    users = {"inglis": new_record("Dr. Inglis", "professor", prof_pw),
             "student1": new_record("Student One", "student", stud_pw),
             "student2": new_record("Student Two", "student", stud_pw)}
    save_users(users)
    lines = ["", "AnatoVision: first run, demo accounts created in " + str(USERS_PATH)]
    lines.append("  professor  inglis     password: " + ("(from DEMO_PROFESSOR_PASSWORD)" if given_prof else prof_pw))
    lines.append("  students   student1, student2   password: " + ("(from DEMO_STUDENT_PASSWORD)" if given_stud else stud_pw))
    lines += ["  Shown once. Not stored anywhere else. Demo login only, not production security.", ""]
    announce("\n".join(lines))
    return True


def locked(username, now=None):
    now = now if now is not None else time.time()
    recent = [t for t in _fails.get(username, []) if now - t < LOCK_SECONDS]
    _fails[username] = recent
    return len(recent) >= MAX_FAILS


def authenticate(username, password, now=None):
    """-> public user dict, or None. Takes the same time for unknown users (no username probing), locks after 5 failures."""
    username = (username or "").strip()
    if locked(username, now):
        return None
    record = load_users().get(username)
    if record is None:
        check_password(password or "", "00" * 16, "00" * 32)       # equal work for unknown names
        ok = False
    else:
        ok = check_password(password or "", record["salt"], record["hash"])
    if not ok:
        _fails.setdefault(username, []).append(now if now is not None else time.time())
        return None
    _fails.pop(username, None)
    return public(username, record)


def students():
    return [(u, r) for u, r in load_users().items() if r["role"] == "student"]


def set_allowed_lectures(username, lectures):
    users = load_users()
    if username not in users or users[username]["role"] != "student":
        raise ValueError(f"{username} is not a student account")
    users[username]["allowed_lectures"] = sorted(set(lectures))
    save_users(users)


def add_student(username, name, password, confirm=None):
    users = load_users()
    username = username.strip()
    if not username or not username.replace("_", "").replace("-", "").replace(".", "").isalnum():
        raise ValueError("the username may use letters, digits, '-', '_' and '.' only")
    if username in users:
        raise ValueError(f"{username} already exists")
    check_password_rules(password, confirm, username)
    users[username] = new_record(name.strip() or username, "student", password)
    save_users(users)


def set_password(username, password, confirm=None):
    users = load_users()
    if username not in users:
        raise ValueError(f"no account {username}")
    check_password_rules(password, confirm, username)
    users[username]["salt"], users[username]["hash"] = hash_password(password)
    save_users(users)
