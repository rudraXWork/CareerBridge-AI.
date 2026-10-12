import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from backend import config


def save(kind, data):
    # One small table is enough for local development.
    with sqlite3.connect(config.DB_PATH) as db:
        db.execute('CREATE TABLE IF NOT EXISTS records '
                   '(id TEXT PRIMARY KEY, kind TEXT, data TEXT, created_at TEXT)')
        rid = uuid4().hex
        db.execute('INSERT INTO records VALUES (?, ?, ?, ?)',
                   (rid, kind, json.dumps(data), datetime.now(timezone.utc).isoformat()))
    return rid
