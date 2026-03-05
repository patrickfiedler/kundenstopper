"""Add video_fit column to displays table."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'kundenstopper.db')


def run():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("ALTER TABLE displays ADD COLUMN video_fit TEXT NOT NULL DEFAULT 'contain'")
        conn.commit()
    except Exception:
        pass  # Column already exists on fresh installs (it's in CREATE TABLE)
    finally:
        conn.close()
