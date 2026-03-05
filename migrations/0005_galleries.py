import sqlite3
import os

DATABASE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'kundenstopper.db')


def run():
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS gallery_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                media_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                original_name TEXT NOT NULL,
                file_size INTEGER NOT NULL DEFAULT 0,
                position INTEGER NOT NULL DEFAULT 0
            )
        ''')
        conn.commit()
        print('Migration 0005: gallery_images table created')
    finally:
        conn.close()
