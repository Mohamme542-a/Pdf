"""تخزين بسيط: قاعدة SQLite + قاموس الترجمة (glossary) الذي يلقّنه الأدمن."""
import json
import os
import re
import sqlite3
import threading
from typing import Dict, List, Tuple

from config import DB_PATH, GLOSSARY_PATH

_lock = threading.Lock()


def _conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _lock, _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                lang TEXT DEFAULT 'ar',
                banned INTEGER DEFAULT 0,
                jobs INTEGER DEFAULT 0,
                joined TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT,
                content TEXT,
                created TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )


# ---------- المستخدمون ----------
def touch_user(user_id: int, username: str = "") -> None:
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO users(user_id, username) VALUES(?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username",
            (user_id, username or ""),
        )


def bump_jobs(user_id: int) -> None:
    with _lock, _conn() as c:
        c.execute("UPDATE users SET jobs = jobs + 1 WHERE user_id=?", (user_id,))


def set_banned(user_id: int, banned: bool) -> None:
    with _lock, _conn() as c:
        c.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
        c.execute("UPDATE users SET banned=? WHERE user_id=?", (1 if banned else 0, user_id))


def is_banned(user_id: int) -> bool:
    with _lock, _conn() as c:
        r = c.execute("SELECT banned FROM users WHERE user_id=?", (user_id,)).fetchone()
        return bool(r and r["banned"])


def all_user_ids() -> List[int]:
    with _lock, _conn() as c:
        return [r["user_id"] for r in c.execute("SELECT user_id FROM users WHERE banned=0")]


def stats() -> Dict[str, int]:
    with _lock, _conn() as c:
        users = c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        jobs = c.execute("SELECT COALESCE(SUM(jobs),0) n FROM users").fetchone()["n"]
        notes = c.execute("SELECT COUNT(*) n FROM notes").fetchone()["n"]
    return {"users": users, "jobs": jobs, "notes": notes}


# ---------- الملاحظات ----------
def add_note(user_id: int, title: str, content: str) -> int:
    with _lock, _conn() as c:
        cur = c.execute(
            "INSERT INTO notes(user_id,title,content) VALUES(?,?,?)", (user_id, title, content)
        )
        return cur.lastrowid


def list_notes(user_id: int) -> List[sqlite3.Row]:
    with _lock, _conn() as c:
        return c.execute(
            "SELECT id,title,created FROM notes WHERE user_id=? ORDER BY id DESC LIMIT 50",
            (user_id,),
        ).fetchall()


def get_note(user_id: int, note_id: int):
    with _lock, _conn() as c:
        return c.execute(
            "SELECT * FROM notes WHERE user_id=? AND id=?", (user_id, note_id)
        ).fetchone()


def delete_note(user_id: int, note_id: int) -> bool:
    with _lock, _conn() as c:
        cur = c.execute("DELETE FROM notes WHERE user_id=? AND id=?", (user_id, note_id))
        return cur.rowcount > 0


# ---------- قاموس الترجمة الذي يلقّنه الأدمن ----------
# البنية: { "ar->en": { "كلمة": "word", ... }, ... }
def load_glossary() -> Dict[str, Dict[str, str]]:
    if not os.path.exists(GLOSSARY_PATH):
        return {}
    try:
        with open(GLOSSARY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_glossary(data: Dict[str, Dict[str, str]]) -> None:
    with open(GLOSSARY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def glossary_pairs() -> List[str]:
    return list(load_glossary().keys())


def add_entries(pair: str, entries: Dict[str, str]) -> int:
    g = load_glossary()
    g.setdefault(pair, {}).update(entries)
    save_glossary(g)
    return len(g[pair])


def delete_pair(pair: str) -> bool:
    g = load_glossary()
    if pair in g:
        del g[pair]
        save_glossary(g)
        return True
    return False


def glossary_size(pair: str) -> int:
    return len(load_glossary().get(pair, {}))


# ---------- تحليل نص الكتاب/القاموس المُلقَّن ----------
LINE_RE = re.compile(r"^\s*(.+?)\s*(?:=|\||:|\t|->|—|–)\s*(.+?)\s*$")


def parse_glossary_text(text: str) -> Dict[str, str]:
    """يقبل أسطراً بالشكل: كلمة = ترجمة / كلمة : ترجمة / كلمة | ترجمة"""
    out: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = LINE_RE.match(line)
        if m:
            src, dst = m.group(1).strip(), m.group(2).strip()
            if src and dst:
                out[src] = dst
    return out


def translate_with_glossary(text: str, pair: str) -> Tuple[str, int]:
    """ترجمة اعتماداً على القاموس المُلقَّن فقط. يرجع (النص، عدد البدائل)."""
    table = load_glossary().get(pair, {})
    if not table:
        return text, 0
    # نرتّب المفاتيح من الأطول للأقصر حتى تُترجم العبارات قبل الكلمات
    keys = sorted(table.keys(), key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(k) for k in keys), re.IGNORECASE)
    count = 0
    lower_map = {k.lower(): v for k, v in table.items()}

    def repl(m):
        nonlocal count
        count += 1
        return lower_map.get(m.group(0).lower(), m.group(0))

    return pattern.sub(repl, text), count
  
