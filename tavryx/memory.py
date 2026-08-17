import sqlite3
import uuid
from datetime import datetime, timezone
from threading import Lock
from .models import Situation, Lifecycle

class MemoryStore:
    def __init__(self, path):
        self.path = str(path)
        self._lock = Lock()
        self._init()

    def _connect(self):
        c = sqlite3.connect(self.path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self._connect() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS situations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                situation_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                sender TEXT NOT NULL,
                channel TEXT NOT NULL,
                input_text TEXT NOT NULL,
                situation_json TEXT NOT NULL
            )""")
            c.execute("""CREATE INDEX IF NOT EXISTS idx_situation_id
                        ON situations(situation_id, id)""")
            c.commit()

    def add(self, sender, channel, input_text, situation):
        if not situation.situation_id:
            situation.situation_id = "S-" + uuid.uuid4().hex[:8].upper()
        situation.updated_at = datetime.now(timezone.utc)
        with self._lock, self._connect() as c:
            c.execute(
                """INSERT INTO situations
                (situation_id,created_at,sender,channel,input_text,situation_json)
                VALUES(?,?,?,?,?,?)""",
                (situation.situation_id, datetime.now(timezone.utc).isoformat(),
                 sender, channel, input_text, situation.model_dump_json())
            )
            c.commit()
        return situation

    def recent(self, limit=30):
        with self._connect() as c:
            rows = c.execute("SELECT * FROM situations ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def latest(self):
        rows = self.recent(1)
        return Situation.model_validate_json(rows[0]["situation_json"]) if rows else None

    def history_for(self, situation_id, limit=12):
        with self._connect() as c:
            rows = c.execute(
                "SELECT * FROM situations WHERE situation_id=? ORDER BY id DESC LIMIT ?",
                (situation_id, limit)
            ).fetchall()
        return [dict(r) for r in rows]

    def candidates(self, sender=None, limit=8):
        # Return the latest state of recent situation threads. This lets the
        # model resume an older situation instead of being trapped by the
        # globally-latest message.
        with self._connect() as c:
            if sender and sender != "unknown":
                rows = c.execute("""
                    SELECT s.* FROM situations s
                    INNER JOIN (
                        SELECT situation_id, MAX(id) AS max_id
                        FROM situations
                        GROUP BY situation_id
                    ) latest ON latest.max_id=s.id
                    WHERE s.sender=? OR s.sender='system'
                    ORDER BY s.id DESC LIMIT ?
                """, (sender, limit)).fetchall()
            else:
                rows = c.execute("""
                    SELECT s.* FROM situations s
                    INNER JOIN (
                        SELECT situation_id, MAX(id) AS max_id
                        FROM situations GROUP BY situation_id
                    ) latest ON latest.max_id=s.id
                    ORDER BY s.id DESC LIMIT ?
                """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def latest_for(self, situation_id):
        with self._connect() as c:
            row = c.execute(
                "SELECT * FROM situations WHERE situation_id=? ORDER BY id DESC LIMIT ?",
                (situation_id, 1)
            ).fetchone()
        return Situation.model_validate_json(row["situation_json"]) if row else None

    def list_situations(self, limit=20):
        with self._connect() as c:
            rows = c.execute("""
                SELECT s.* FROM situations s
                INNER JOIN (
                    SELECT situation_id, MAX(id) AS max_id
                    FROM situations GROUP BY situation_id
                ) latest ON latest.max_id = s.id
                ORDER BY s.id DESC LIMIT ?
            """, (limit,)).fetchall()
        return [Situation.model_validate_json(r["situation_json"]) for r in rows]

    def park(self, situation_id):
        s = self.latest_for(situation_id)
        if not s:
            return None
        s.lifecycle = Lifecycle.PARKED
        s.state_delta = "Situation parked. Its context remains available for resume."
        return self.add("system", "tavryx", "park", s)

    def resume(self, situation_id):
        s = self.latest_for(situation_id)
        if not s:
            return None
        s.lifecycle = Lifecycle.ACTIVE
        s.state_delta = "Situation resumed with its previous context and decision history."
        return self.add("system", "tavryx", "resume", s)

    def clear(self):
        with self._lock, self._connect() as c:
            c.execute("DELETE FROM situations")
            c.commit()
