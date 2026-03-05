import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager

DATABASE_PATH = 'kundenstopper.db'


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize the database with required tables and migrate legacy data."""
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS displays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                width INTEGER NOT NULL DEFAULT 1920,
                height INTEGER NOT NULL DEFAULT 1080,
                selected_media_id INTEGER NOT NULL DEFAULT 0,
                cycle_interval INTEGER NOT NULL DEFAULT 10,
                background_color TEXT NOT NULL DEFAULT '#ffffff',
                progress_indicator TEXT NOT NULL DEFAULT 'progress',
                video_fit TEXT NOT NULL DEFAULT 'contain'
            )
        ''')

        # Migrate: add video_fit column if upgrading from older schema
        try:
            conn.execute("ALTER TABLE displays ADD COLUMN video_fit TEXT NOT NULL DEFAULT 'contain'")
        except Exception:
            pass  # Column already exists

        conn.execute('''
            CREATE TABLE IF NOT EXISTS media_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_type TEXT NOT NULL,
                filename TEXT,
                original_name TEXT NOT NULL,
                url TEXT,
                upload_date TIMESTAMP NOT NULL,
                file_size INTEGER NOT NULL DEFAULT 0,
                scale_to_fit INTEGER NOT NULL DEFAULT 0
            )
        ''')

        # Migrate: add scale_to_fit column if upgrading from older schema
        try:
            conn.execute("ALTER TABLE media_items ADD COLUMN scale_to_fit INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass  # Column already exists

        conn.execute('''
            CREATE TABLE IF NOT EXISTS pdf_renders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                media_id INTEGER NOT NULL,
                display_id INTEGER NOT NULL,
                page_number INTEGER NOT NULL,
                render_filename TEXT NOT NULL,
                UNIQUE(media_id, display_id, page_number)
            )
        ''')

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

        conn.execute('''
            CREATE TABLE IF NOT EXISTS playlist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                display_id INTEGER NOT NULL,
                media_id INTEGER NOT NULL,
                duration INTEGER NOT NULL DEFAULT 10,
                position INTEGER NOT NULL DEFAULT 0
            )
        ''')

        # Global settings (auto-cleanup only; display settings live in displays table)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_cleanup_enabled', 'true')")
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_cleanup_days', '180')")

        # --- Migrate legacy pdf_files table if present ---
        legacy_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pdf_files'"
        ).fetchone()

        if legacy_table:
            migrated = conn.execute(
                "SELECT COUNT(*) FROM media_items WHERE content_type = 'pdf'"
            ).fetchone()[0]

            if migrated == 0:
                old_pdfs = conn.execute(
                    'SELECT * FROM pdf_files ORDER BY upload_date ASC'
                ).fetchall()
                for pdf in old_pdfs:
                    conn.execute(
                        '''INSERT OR IGNORE INTO media_items
                           (content_type, filename, original_name, upload_date, file_size)
                           VALUES (?, ?, ?, ?, ?)''',
                        ('pdf', pdf['filename'], pdf['original_name'],
                         pdf['upload_date'], pdf['file_size'])
                    )

        # --- Create default display if none exist ---
        if conn.execute('SELECT COUNT(*) FROM displays').fetchone()[0] == 0:
            # Pull legacy per-display settings if available
            def _legacy(key, default):
                row = conn.execute(
                    'SELECT value FROM settings WHERE key = ?', (key,)
                ).fetchone()
                return row['value'] if row else default

            cycle_interval = int(_legacy('cycle_interval', '10'))
            background_color = _legacy('background_color', '#ffffff')
            progress_indicator = _legacy('progress_indicator', 'progress')

            # Map legacy selected_pdf_id → media_item id
            selected_media_id = 0
            old_sel_id = int(_legacy('selected_pdf_id', '0'))
            if old_sel_id > 0 and legacy_table:
                old_pdf = conn.execute(
                    'SELECT filename FROM pdf_files WHERE id = ?', (old_sel_id,)
                ).fetchone()
                if old_pdf:
                    media = conn.execute(
                        'SELECT id FROM media_items WHERE filename = ?',
                        (old_pdf['filename'],)
                    ).fetchone()
                    if media:
                        selected_media_id = media['id']

            conn.execute(
                '''INSERT INTO displays
                   (name, slug, width, height, selected_media_id,
                    cycle_interval, background_color, progress_indicator)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                ('Standard', 'default', 1920, 1080, selected_media_id,
                 cycle_interval, background_color, progress_indicator)
            )


# ---------- global settings ----------

def get_setting(key, default=None):
    with get_db() as conn:
        result = conn.execute(
            'SELECT value FROM settings WHERE key = ?', (key,)
        ).fetchone()
        return result['value'] if result else default


def set_setting(key, value):
    with get_db() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
            (key, str(value))
        )


# ---------- displays ----------

def get_all_displays():
    with get_db() as conn:
        return conn.execute('SELECT * FROM displays ORDER BY id').fetchall()


def get_display(display_id):
    with get_db() as conn:
        return conn.execute(
            'SELECT * FROM displays WHERE id = ?', (display_id,)
        ).fetchone()


def get_display_by_slug(slug):
    with get_db() as conn:
        return conn.execute(
            'SELECT * FROM displays WHERE slug = ?', (slug,)
        ).fetchone()


def create_display(name, slug, width, height):
    with get_db() as conn:
        conn.execute(
            'INSERT INTO displays (name, slug, width, height) VALUES (?, ?, ?, ?)',
            (name, slug, width, height)
        )
        return conn.execute('SELECT last_insert_rowid()').fetchone()[0]


def update_display(display_id, **kwargs):
    allowed = {'name', 'width', 'height', 'selected_media_id',
               'cycle_interval', 'background_color', 'progress_indicator', 'video_fit'}
    fields = [(k, v) for k, v in kwargs.items() if k in allowed and v is not None]
    if not fields:
        return
    set_clause = ', '.join(f'{k} = ?' for k, _ in fields)
    values = [v for _, v in fields] + [display_id]
    with get_db() as conn:
        conn.execute(f'UPDATE displays SET {set_clause} WHERE id = ?', values)


def delete_display(display_id):
    with get_db() as conn:
        conn.execute('DELETE FROM playlist_items WHERE display_id = ?', (display_id,))
        conn.execute('DELETE FROM displays WHERE id = ?', (display_id,))


# ---------- media items ----------

def add_media(content_type, original_name, filename=None, url=None, file_size=0, scale_to_fit=False):
    with get_db() as conn:
        conn.execute(
            '''INSERT INTO media_items
               (content_type, filename, original_name, url, upload_date, file_size, scale_to_fit)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (content_type, filename, original_name, url, datetime.now(), file_size, 1 if scale_to_fit else 0)
        )
        return conn.execute('SELECT last_insert_rowid()').fetchone()[0]


def get_media(media_id):
    with get_db() as conn:
        return conn.execute(
            'SELECT * FROM media_items WHERE id = ?', (media_id,)
        ).fetchone()


def get_all_media(limit=None, offset=0):
    with get_db() as conn:
        if limit:
            return conn.execute(
                'SELECT * FROM media_items ORDER BY upload_date DESC LIMIT ? OFFSET ?',
                (limit, offset)
            ).fetchall()
        return conn.execute(
            'SELECT * FROM media_items ORDER BY upload_date DESC'
        ).fetchall()


def get_url_media_by_url(url):
    """Return the media_item with content_type='url' matching this URL, or None."""
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM media_items WHERE content_type = 'url' AND url = ?", (url,)
        ).fetchone()


def get_all_pdf_media():
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM media_items WHERE content_type = 'pdf'"
        ).fetchall()


def get_media_count():
    with get_db() as conn:
        return conn.execute('SELECT COUNT(*) FROM media_items').fetchone()[0]


def get_newest_media():
    with get_db() as conn:
        return conn.execute(
            'SELECT * FROM media_items ORDER BY upload_date DESC LIMIT 1'
        ).fetchone()


def update_media_scale_to_fit(media_id, scale_to_fit):
    with get_db() as conn:
        conn.execute(
            'UPDATE media_items SET scale_to_fit = ? WHERE id = ?',
            (1 if scale_to_fit else 0, media_id)
        )


def update_media_url(media_id, url):
    with get_db() as conn:
        conn.execute('UPDATE media_items SET url = ? WHERE id = ?', (url, media_id))


def update_media_name(media_id, new_name):
    with get_db() as conn:
        conn.execute(
            'UPDATE media_items SET original_name = ? WHERE id = ?',
            (new_name, media_id)
        )


def delete_media(media_id):
    """Delete a media item. Returns dict {filename, renders} for filesystem cleanup."""
    with get_db() as conn:
        item = conn.execute(
            'SELECT * FROM media_items WHERE id = ?', (media_id,)
        ).fetchone()
        if not item:
            return None

        renders = conn.execute(
            'SELECT display_id, render_filename FROM pdf_renders WHERE media_id = ?',
            (media_id,)
        ).fetchall()

        gallery_images = []
        if item['content_type'] == 'gallery':
            gallery_images = conn.execute(
                'SELECT filename FROM gallery_images WHERE media_id = ?', (media_id,)
            ).fetchall()
            conn.execute('DELETE FROM gallery_images WHERE media_id = ?', (media_id,))

        conn.execute('DELETE FROM pdf_renders WHERE media_id = ?', (media_id,))
        conn.execute('DELETE FROM playlist_items WHERE media_id = ?', (media_id,))
        conn.execute('DELETE FROM media_items WHERE id = ?', (media_id,))
        conn.execute(
            'UPDATE displays SET selected_media_id = 0 WHERE selected_media_id = ?',
            (media_id,)
        )

        return {
            'filename': item['filename'],
            'renders': [(r['display_id'], r['render_filename']) for r in renders],
            'gallery_images': [r['filename'] for r in gallery_images],
        }


# ---------- pdf renders ----------

def add_pdf_render(media_id, display_id, page_number, render_filename):
    with get_db() as conn:
        conn.execute(
            '''INSERT OR REPLACE INTO pdf_renders
               (media_id, display_id, page_number, render_filename)
               VALUES (?, ?, ?, ?)''',
            (media_id, display_id, page_number, render_filename)
        )


def get_pdf_renders(media_id, display_id):
    with get_db() as conn:
        return conn.execute(
            '''SELECT * FROM pdf_renders
               WHERE media_id = ? AND display_id = ?
               ORDER BY page_number''',
            (media_id, display_id)
        ).fetchall()


def delete_pdf_renders(media_id, display_id):
    """Delete renders for a media+display pair. Returns list of render filenames."""
    with get_db() as conn:
        renders = conn.execute(
            '''SELECT render_filename FROM pdf_renders
               WHERE media_id = ? AND display_id = ?''',
            (media_id, display_id)
        ).fetchall()
        conn.execute(
            'DELETE FROM pdf_renders WHERE media_id = ? AND display_id = ?',
            (media_id, display_id)
        )
        return [r['render_filename'] for r in renders]


def delete_pdf_renders_for_display(display_id):
    """Delete all renders for a display. Returns list of render filenames."""
    with get_db() as conn:
        renders = conn.execute(
            'SELECT render_filename FROM pdf_renders WHERE display_id = ?',
            (display_id,)
        ).fetchall()
        conn.execute('DELETE FROM pdf_renders WHERE display_id = ?', (display_id,))
        return [r['render_filename'] for r in renders]


# ---------- cleanup ----------

def cleanup_old_media(upload_folder):
    """Delete file-based media items older than the configured threshold."""
    from datetime import timedelta

    if get_setting('auto_cleanup_enabled', 'true').lower() != 'true':
        return 0

    cleanup_days = int(get_setting('auto_cleanup_days', '180'))
    cutoff_date = datetime.now() - timedelta(days=cleanup_days)

    with get_db() as conn:
        # Collect all actively-selected media IDs across displays
        active_ids = set()
        displays = conn.execute('SELECT id, selected_media_id FROM displays').fetchall()
        for d in displays:
            sid = d['selected_media_id']
            if sid == 0:
                newest = conn.execute(
                    'SELECT id FROM media_items ORDER BY upload_date DESC LIMIT 1'
                ).fetchone()
                if newest:
                    active_ids.add(newest['id'])
            else:
                active_ids.add(sid)

        if active_ids:
            placeholders = ','.join('?' * len(active_ids))
            old_items = conn.execute(
                f'''SELECT * FROM media_items
                    WHERE upload_date < ?
                    AND filename IS NOT NULL
                    AND id NOT IN ({placeholders})''',
                [cutoff_date, *active_ids]
            ).fetchall()
        else:
            old_items = conn.execute(
                '''SELECT * FROM media_items
                   WHERE upload_date < ? AND filename IS NOT NULL''',
                (cutoff_date,)
            ).fetchall()

        deleted_count = 0
        for item in old_items:
            renders = conn.execute(
                'SELECT display_id, render_filename FROM pdf_renders WHERE media_id = ?',
                (item['id'],)
            ).fetchall()
            conn.execute('DELETE FROM pdf_renders WHERE media_id = ?', (item['id'],))
            conn.execute('DELETE FROM media_items WHERE id = ?', (item['id'],))

            filepath = os.path.join(upload_folder, item['filename'])
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    deleted_count += 1
                except OSError:
                    pass

            for r in renders:
                render_path = os.path.join('renders', str(r['display_id']), r['render_filename'])
                if os.path.exists(render_path):
                    try:
                        os.remove(render_path)
                    except OSError:
                        pass

        return deleted_count


# ---------- playlists ----------

def get_playlist_items(display_id):
    """Return ordered playlist items joined with media info."""
    with get_db() as conn:
        return conn.execute(
            '''SELECT pi.id, pi.display_id, pi.media_id, pi.duration, pi.position,
                      m.content_type, m.original_name, m.filename, m.url, m.scale_to_fit
               FROM playlist_items pi
               JOIN media_items m ON pi.media_id = m.id
               WHERE pi.display_id = ?
               ORDER BY pi.position''',
            (display_id,)
        ).fetchall()


def add_playlist_item(display_id, media_id, duration):
    with get_db() as conn:
        max_pos = conn.execute(
            'SELECT COALESCE(MAX(position), 0) FROM playlist_items WHERE display_id = ?',
            (display_id,)
        ).fetchone()[0]
        conn.execute(
            'INSERT INTO playlist_items (display_id, media_id, duration, position) VALUES (?, ?, ?, ?)',
            (display_id, media_id, duration, max_pos + 1)
        )
        return conn.execute('SELECT last_insert_rowid()').fetchone()[0]


def remove_playlist_item(item_id, display_id):
    with get_db() as conn:
        conn.execute(
            'DELETE FROM playlist_items WHERE id = ? AND display_id = ?',
            (item_id, display_id)
        )
        # Repack positions to stay gapless
        items = conn.execute(
            'SELECT id FROM playlist_items WHERE display_id = ? ORDER BY position',
            (display_id,)
        ).fetchall()
        for i, row in enumerate(items, 1):
            conn.execute('UPDATE playlist_items SET position = ? WHERE id = ?', (i, row['id']))


def update_playlist_item_duration(item_id, display_id, duration):
    with get_db() as conn:
        conn.execute(
            'UPDATE playlist_items SET duration = ? WHERE id = ? AND display_id = ?',
            (duration, item_id, display_id)
        )


def reorder_playlist_items(display_id, ordered_ids):
    """Set positions from an ordered list of item IDs."""
    with get_db() as conn:
        for i, item_id in enumerate(ordered_ids, 1):
            conn.execute(
                'UPDATE playlist_items SET position = ? WHERE id = ? AND display_id = ?',
                (i, item_id, display_id)
            )


def move_playlist_item(item_id, display_id, direction):
    """Swap item with its neighbour. direction: -1 = up, +1 = down."""
    with get_db() as conn:
        items = conn.execute(
            'SELECT id, position FROM playlist_items WHERE display_id = ? ORDER BY position',
            (display_id,)
        ).fetchall()
        ids = [row['id'] for row in items]
        if item_id not in ids:
            return
        idx = ids.index(item_id)
        swap_idx = idx + direction
        if swap_idx < 0 or swap_idx >= len(ids):
            return
        pos_a = items[idx]['position']
        pos_b = items[swap_idx]['position']
        conn.execute('UPDATE playlist_items SET position = ? WHERE id = ?', (pos_b, ids[idx]))
        conn.execute('UPDATE playlist_items SET position = ? WHERE id = ?', (pos_a, ids[swap_idx]))


# ---------- galleries ----------

def add_gallery(name):
    with get_db() as conn:
        conn.execute(
            'INSERT INTO media_items (content_type, original_name, upload_date, file_size) VALUES (?, ?, ?, ?)',
            ('gallery', name, datetime.now(), 0)
        )
        return conn.execute('SELECT last_insert_rowid()').fetchone()[0]


def get_gallery_images(media_id):
    with get_db() as conn:
        return conn.execute(
            'SELECT * FROM gallery_images WHERE media_id = ? ORDER BY position',
            (media_id,)
        ).fetchall()


def add_gallery_image(media_id, filename, original_name, file_size):
    with get_db() as conn:
        max_pos = conn.execute(
            'SELECT COALESCE(MAX(position), 0) FROM gallery_images WHERE media_id = ?',
            (media_id,)
        ).fetchone()[0]
        conn.execute(
            'INSERT INTO gallery_images (media_id, filename, original_name, file_size, position) VALUES (?, ?, ?, ?, ?)',
            (media_id, filename, original_name, file_size, max_pos + 1)
        )
        return conn.execute('SELECT last_insert_rowid()').fetchone()[0]


def remove_gallery_image(image_id, media_id):
    """Delete one image from a gallery. Returns filename for filesystem cleanup, or None."""
    with get_db() as conn:
        row = conn.execute(
            'SELECT filename FROM gallery_images WHERE id = ? AND media_id = ?',
            (image_id, media_id)
        ).fetchone()
        if not row:
            return None
        conn.execute(
            'DELETE FROM gallery_images WHERE id = ? AND media_id = ?',
            (image_id, media_id)
        )
        items = conn.execute(
            'SELECT id FROM gallery_images WHERE media_id = ? ORDER BY position',
            (media_id,)
        ).fetchall()
        for i, r in enumerate(items, 1):
            conn.execute('UPDATE gallery_images SET position = ? WHERE id = ?', (i, r['id']))
        return row['filename']


def reorder_gallery_images(media_id, ordered_ids):
    with get_db() as conn:
        for i, image_id in enumerate(ordered_ids, 1):
            conn.execute(
                'UPDATE gallery_images SET position = ? WHERE id = ? AND media_id = ?',
                (i, image_id, media_id)
            )
