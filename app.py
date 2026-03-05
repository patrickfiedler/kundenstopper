import os
import re
import uuid
import glob as glob_module
import subprocess
import requests as http_requests
from urllib.parse import urlparse, parse_qs
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, abort, Response
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
import bcrypt

from config import config
from models import (
    init_db,
    get_setting, set_setting,
    get_all_displays, get_display, get_display_by_slug,
    create_display, update_display, delete_display,
    add_media, get_media, get_all_media, get_all_pdf_media,
    get_media_count, get_newest_media, update_media_name, delete_media,
    add_pdf_render, get_pdf_renders, delete_pdf_renders,
    delete_pdf_renders_for_display,
    cleanup_old_media,
    get_url_media_by_url,
    update_media_scale_to_fit,
    update_media_url,
    get_playlist_items, add_playlist_item, remove_playlist_item,
    update_playlist_item_duration, move_playlist_item, reorder_playlist_items,
    add_gallery, get_gallery_images, add_gallery_image,
    remove_gallery_image, reorder_gallery_images,
)

app = Flask(__name__)
app.config['SECRET_KEY'] = config.secret_key
app.config['UPLOAD_FOLDER'] = config.upload_folder
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB

RENDERS_FOLDER = 'renders'

COOKIE_HIDE_CSS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookie_hide.conf')

# JS injected when scale-to-fit is requested: scales the page to fill the iframe viewport.
PROXY_SCALE_JS = """<script>
(function() {
    function scaleToFit() {
        var vw = window.innerWidth;
        var pw = document.documentElement.scrollWidth;
        if (!pw || pw === vw) return;
        var scale = vw / pw;
        document.documentElement.style.transformOrigin = '0 0';
        document.documentElement.style.transform = 'scale(' + scale + ')';
        document.body.style.overflow = 'hidden';
    }
    window.addEventListener('load', scaleToFit);
    window.addEventListener('resize', scaleToFit);
})();
</script>"""

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(RENDERS_FOLDER, exist_ok=True)

init_db()

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Allowed upload extensions mapped to content type
ALLOWED_EXTENSIONS = {
    'pdf': 'pdf',
    'jpg': 'image', 'jpeg': 'image', 'png': 'image', 'gif': 'image', 'webp': 'image',
    'mp4': 'video', 'webm': 'video', 'mov': 'video',
}


class User(UserMixin):
    def __init__(self, username):
        self.id = username
        self.username = username


@login_manager.user_loader
def load_user(user_id):
    if user_id == config.admin_username:
        return User(user_id)
    return None


def verify_password(password):
    password_hash = config.admin_password_hash
    if not password_hash:
        return False
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


# ---------- PDF rendering ----------

def _dpi_for_display(width, height):
    """Calculate a suitable render DPI for a given display resolution."""
    dpi = round(max(width, height) / 7)
    return max(100, min(300, dpi))


def render_pdf_for_display(filepath, media_id, display):
    """Pre-render all pages of a PDF as PNGs for one display. Returns page count."""
    display_id = display['id']
    render_dir = os.path.join(RENDERS_FOLDER, str(display_id))
    os.makedirs(render_dir, exist_ok=True)

    # Remove stale renders for this media+display
    old_renders = delete_pdf_renders(media_id, display_id)
    for fname in old_renders:
        old_path = os.path.join(render_dir, fname)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass

    dpi = _dpi_for_display(display['width'], display['height'])
    prefix = str(uuid.uuid4())
    prefix_path = os.path.join(render_dir, prefix)

    try:
        result = subprocess.run(
            ['pdftoppm', '-r', str(dpi), '-png', filepath, prefix_path],
            capture_output=True, text=True, timeout=120
        )
    except FileNotFoundError:
        raise RuntimeError(
            'pdftoppm nicht gefunden. Bitte poppler-utils installieren: '
            'sudo apt install poppler-utils'
        )

    if result.returncode != 0:
        raise RuntimeError(f'pdftoppm Fehler: {result.stderr.strip()}')

    # Sort pages numerically (pdftoppm pads with leading zeros)
    pages = sorted(
        glob_module.glob(f'{prefix_path}-*.png'),
        key=lambda p: int(re.search(r'-(\d+)\.png$', p).group(1))
    )

    if not pages:
        raise RuntimeError('pdftoppm hat keine Seiten ausgegeben — ist die PDF-Datei gültig?')

    for i, page_path in enumerate(pages, 1):
        add_pdf_render(media_id, display_id, i, os.path.basename(page_path))

    return len(pages)


def render_pdf_for_all_displays(filepath, media_id):
    """Render a PDF for every existing display. Returns dict {display_id: page_count or error}."""
    results = {}
    for display in get_all_displays():
        try:
            results[display['id']] = render_pdf_for_display(filepath, media_id, display)
        except RuntimeError as e:
            results[display['id']] = str(e)
    return results


# ---------- URL helpers ----------

def make_youtube_embed_with_params(video_id, controls=False, cc=False, cc_lang='', rel=False):
    """Build a YouTube embed URL from a video ID and display options."""
    params = [
        'autoplay=1', 'mute=1', 'loop=1', f'playlist={video_id}',
        f'controls={"1" if controls else "0"}',
        f'rel={"1" if rel else "0"}',
        'iv_load_policy=3',  # hide annotations
    ]
    if cc:
        params.append('cc_load_policy=1')
        if cc_lang.strip():
            params.append(f'cc_lang_pref={cc_lang.strip()}')
    return f'https://www.youtube.com/embed/{video_id}?' + '&'.join(params)


def make_youtube_embed(url):
    """Convert a YouTube watch/short URL to an embed URL with sensible signage defaults."""
    for pattern in (r'youtube\.com/watch\?.*v=([a-zA-Z0-9_-]+)',
                    r'youtu\.be/([a-zA-Z0-9_-]+)'):
        m = re.search(pattern, url)
        if m:
            return make_youtube_embed_with_params(m.group(1))
    return url


def parse_youtube_params(embed_url):
    """Extract current embed options from a stored YouTube embed URL."""
    try:
        params = parse_qs(urlparse(embed_url).query)
        return {
            'controls': params.get('controls', ['0'])[0] == '1',
            'cc':       'cc_load_policy' in params,
            'cc_lang':  params.get('cc_lang_pref', [''])[0],
            'rel':      params.get('rel', ['0'])[0] == '1',
        }
    except Exception:
        return {'controls': False, 'cc': False, 'cc_lang': '', 'rel': False}


def detect_url_content_type(url):
    """Detect content type for a URL entry."""
    if re.search(r'youtube\.com|youtu\.be', url, re.IGNORECASE):
        return 'youtube'
    return 'url'


# ---------- Public routes ----------

@app.route('/')
def index():
    displays = get_all_displays()
    if displays:
        return redirect(url_for('display_by_slug', slug=displays[0]['slug']))
    return redirect(url_for('display_by_slug', slug='default'))


@app.route('/display')
def display_legacy():
    """Backwards-compatible redirect to first display."""
    displays = get_all_displays()
    slug = displays[0]['slug'] if displays else 'default'
    return redirect(url_for('display_by_slug', slug=slug))


@app.route('/display/<slug>')
def display_by_slug(slug):
    display = get_display_by_slug(slug)
    if not display:
        abort(404)
    return render_template('display.html', slug=slug)


def _media_to_item(media, display):
    """Serialize a media item for the display API (used in both single and playlist mode)."""
    item = {'content_type': media['content_type'], 'original_name': media['original_name']}
    if media['content_type'] == 'pdf':
        renders = get_pdf_renders(media['id'], display['id'])
        item['pages'] = [
            url_for('serve_render', display_id=display['id'], filename=r['render_filename'])
            for r in renders
        ]
    elif media['content_type'] == 'gallery':
        images = get_gallery_images(media['id'])
        item['pages'] = [
            url_for('serve_upload', filename=img['filename'])
            for img in images
        ]
    elif media['content_type'] in ('image', 'video'):
        item['url'] = url_for('serve_upload', filename=media['filename'])
        if media['content_type'] == 'video':
            item['video_fit'] = display['video_fit'] or 'contain'
    else:  # youtube, url
        item['url'] = media['url']
        if media['content_type'] == 'url':
            item['scale_to_fit'] = bool(media['scale_to_fit'])
    return item


@app.route('/api/display/<slug>')
def display_api(slug):
    """API endpoint: current content info for a display."""
    display = get_display_by_slug(slug)
    if not display:
        return jsonify({'error': 'Display nicht gefunden'}), 404

    common = {
        'background_color': display['background_color'],
        'progress_indicator': display['progress_indicator'],
    }

    # --- Playlist mode ---
    playlist = get_playlist_items(display['id'])
    if playlist:
        items = []
        for pi in playlist:
            media = get_media(pi['media_id'])
            if not media:
                continue
            item = _media_to_item(media, display)
            item['duration'] = pi['duration']
            items.append(item)
        if items:
            return jsonify({**common, 'mode': 'playlist', 'items': items})

    # --- Single item mode ---
    selected_id = display['selected_media_id']
    media = get_newest_media() if selected_id == 0 else get_media(selected_id)
    if not media:
        return jsonify({'error': 'Kein Inhalt verfügbar'}), 404

    response = {
        **common,
        'cycle_interval': display['cycle_interval'],
        'video_fit': display['video_fit'] or 'contain',
        **_media_to_item(media, display),
    }
    return jsonify(response)


@app.route('/api/current-pdf')
def current_pdf_legacy():
    """Backwards-compatible API: proxies to first display's API."""
    displays = get_all_displays()
    if not displays:
        return jsonify({'error': 'Keine Anzeige konfiguriert'}), 404
    return display_api(displays[0]['slug'])


@app.route('/uploads/<filename>')
def serve_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/renders/<int:display_id>/<filename>')
def serve_render(display_id, filename):
    render_dir = os.path.join(RENDERS_FOLDER, str(display_id))
    return send_from_directory(render_dir, filename)


@app.route('/proxy')
def proxy():
    """Fetch a website server-side and strip X-Frame-Options/CSP headers for iframe embedding.
    Security: only whitelisted URLs (registered url-type media items) are proxied."""
    url = request.args.get('url', '').strip()
    if not url or not url.startswith(('http://', 'https://')):
        abort(400)

    # Whitelist check: only proxy URLs that exist as url-type media items
    if not get_url_media_by_url(url):
        abort(403)

    try:
        resp = http_requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; Kundenstopper/1.0)'
        })
    except http_requests.RequestException:
        abort(502)

    ct = resp.headers.get('content-type', 'text/html')

    # For HTML: inject <base href>, cookie-hiding CSS, and optionally scale-to-fit JS
    if 'text/html' in ct:
        try:
            cookie_css = f'<style>{open(COOKIE_HIDE_CSS_FILE).read()}</style>'
        except OSError:
            cookie_css = ''
        scale_js = PROXY_SCALE_JS if request.args.get('scale') == 'fit' else ''
        inject = f'<base href="{url}">' + cookie_css + scale_js
        html = resp.text
        if re.search(r'<head', html, re.IGNORECASE):
            html = re.sub(r'(<head[^>]*>)', lambda m: m.group(1) + inject,
                          html, count=1, flags=re.IGNORECASE)
        else:
            html = inject + html
        content = html.encode('utf-8', errors='replace')
        ct = 'text/html; charset=utf-8'
    else:
        content = resp.content

    # Forward headers, stripping hop-by-hop headers (forbidden in WSGI per PEP 3333)
    # and headers that block iframe embedding or conflict with Flask response handling
    skip = {
        # Hop-by-hop (connection-layer, must not be forwarded)
        'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
        'te', 'trailers', 'transfer-encoding', 'upgrade',
        # Proxy-specific
        'x-frame-options', 'content-encoding', 'content-length',
    }
    headers = {}
    for key, value in resp.headers.items():
        k = key.lower()
        if k in skip:
            continue
        if k == 'content-security-policy':
            # Remove frame-ancestors directive only; keep the rest of CSP intact
            value = re.sub(r'frame-ancestors\s+[^;]*;?\s*', '', value, flags=re.IGNORECASE).strip('; ')
            if not value:
                continue
        headers[key] = value
    headers['Content-Type'] = ct

    return Response(content, status=resp.status_code, headers=headers)


# ---------- Auth ----------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == config.admin_username and verify_password(password):
            login_user(User(username))
            return redirect(url_for('admin'))
        flash('Ungültiger Benutzername oder Passwort', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ---------- Admin ----------

@app.route('/admin')
@login_required
def admin():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    media_list = get_all_media(limit=per_page, offset=offset)
    total_media = get_media_count()
    total_pages = (total_media + per_page - 1) // per_page

    displays = get_all_displays()

    # For each display, resolve what's currently showing
    display_current = {}
    for d in displays:
        sid = d['selected_media_id']
        display_current[d['id']] = get_newest_media() if sid == 0 else get_media(sid)

    # For each media item, collect which display IDs have it selected
    selected_on = {}  # media_id → list of display ids
    for d in displays:
        sid = d['selected_media_id']
        if sid != 0:
            selected_on.setdefault(sid, []).append(d['id'])

    auto_cleanup_enabled = get_setting('auto_cleanup_enabled', 'true')
    auto_cleanup_days = int(get_setting('auto_cleanup_days', '180'))

    display_playlists = {d['id']: get_playlist_items(d['id']) for d in displays}
    all_media = get_all_media()  # unpaginated, for playlist dropdowns

    youtube_params = {
        item['id']: parse_youtube_params(item['url'])
        for item in media_list
        if item['content_type'] == 'youtube' and item['url']
    }

    gallery_images_map = {
        item['id']: get_gallery_images(item['id'])
        for item in all_media
        if item['content_type'] == 'gallery'
    }
    gallery_image_counts = {mid: len(imgs) for mid, imgs in gallery_images_map.items()}

    return render_template(
        'admin.html',
        displays=displays,
        display_current=display_current,
        display_playlists=display_playlists,
        all_media=all_media,
        media_list=media_list,
        page=page,
        total_pages=total_pages,
        selected_on=selected_on,
        auto_cleanup_enabled=auto_cleanup_enabled,
        auto_cleanup_days=auto_cleanup_days,
        youtube_params=youtube_params,
        gallery_images_map=gallery_images_map,
        gallery_image_counts=gallery_image_counts,
    )


# --- Display management ---

@app.route('/admin/display/create', methods=['POST'])
@login_required
def create_display_route():
    name = request.form.get('name', '').strip()
    slug = request.form.get('slug', '').strip().lower()
    width = request.form.get('width', type=int)
    height = request.form.get('height', type=int)

    if not name or not slug or not width or not height:
        flash('Alle Felder sind erforderlich', 'error')
        return redirect(url_for('admin'))

    if not re.match(r'^[a-z0-9][a-z0-9-]*$', slug):
        flash('URL-Kürzel darf nur Kleinbuchstaben, Ziffern und Bindestriche enthalten', 'error')
        return redirect(url_for('admin'))

    if get_display_by_slug(slug):
        flash(f'URL-Kürzel "{slug}" ist bereits vergeben', 'error')
        return redirect(url_for('admin'))

    display_id = create_display(name, slug, width, height)
    display = get_display(display_id)

    # Render all existing PDFs for this new display
    errors = []
    for media in get_all_pdf_media():
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], media['filename'])
        if os.path.exists(filepath):
            try:
                render_pdf_for_display(filepath, media['id'], display)
            except RuntimeError as e:
                errors.append(f'{media["original_name"]}: {e}')

    if errors:
        flash(f'Display "{name}" erstellt. Render-Fehler: ' + '; '.join(errors), 'error')
    else:
        flash(f'Display "{name}" erfolgreich erstellt', 'success')

    return redirect(url_for('admin'))


@app.route('/admin/display/<int:display_id>/settings', methods=['POST'])
@login_required
def update_display_settings(display_id):
    display = get_display(display_id)
    if not display:
        flash('Display nicht gefunden', 'error')
        return redirect(url_for('admin'))

    name = request.form.get('name', '').strip()
    width = request.form.get('width', type=int)
    height = request.form.get('height', type=int)
    cycle_interval = request.form.get('cycle_interval', type=int)
    background_color = request.form.get('background_color', '').strip()
    progress_indicator = request.form.get('progress_indicator', '').strip()
    video_fit = request.form.get('video_fit', '').strip()

    errors = []
    if not name:
        errors.append('Name darf nicht leer sein')
    if not width or width < 1:
        errors.append('Ungültige Breite')
    if not height or height < 1:
        errors.append('Ungültige Höhe')
    if not cycle_interval or cycle_interval < 1:
        errors.append('Ungültiges Wechselintervall')
    if not (background_color and len(background_color) == 7 and background_color.startswith('#')):
        errors.append('Ungültige Hintergrundfarbe')
    if progress_indicator not in ('progress', 'subtle', 'countdown', 'none'):
        errors.append('Ungültige Fortschrittsanzeige')
    if video_fit not in ('contain', 'cover'):
        errors.append('Ungültige Videoskalierung')

    if errors:
        for e in errors:
            flash(e, 'error')
        return redirect(url_for('admin'))

    resolution_changed = (width != display['width'] or height != display['height'])

    update_display(display_id, name=name, width=width, height=height,
                   cycle_interval=cycle_interval, background_color=background_color,
                   progress_indicator=progress_indicator, video_fit=video_fit)

    if resolution_changed:
        display = get_display(display_id)
        render_errors = []
        for media in get_all_pdf_media():
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], media['filename'])
            if os.path.exists(filepath):
                try:
                    render_pdf_for_display(filepath, media['id'], display)
                except RuntimeError as e:
                    render_errors.append(f'{media["original_name"]}: {e}')
        if render_errors:
            flash('Einstellungen gespeichert. Render-Fehler: ' + '; '.join(render_errors), 'error')
        else:
            flash(f'Einstellungen gespeichert, PDFs für neue Auflösung neu gerendert', 'success')
    else:
        flash('Einstellungen gespeichert', 'success')

    return redirect(url_for('admin'))


@app.route('/admin/display/<int:display_id>/delete', methods=['POST'])
@login_required
def delete_display_route(display_id):
    displays = get_all_displays()
    if len(displays) <= 1:
        flash('Das letzte Display kann nicht gelöscht werden', 'error')
        return redirect(url_for('admin'))

    # Clean up render files
    render_filenames = delete_pdf_renders_for_display(display_id)
    render_dir = os.path.join(RENDERS_FOLDER, str(display_id))
    for fname in render_filenames:
        path = os.path.join(render_dir, fname)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    delete_display(display_id)
    flash('Display gelöscht', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/display/<int:display_id>/select/<int:media_id>', methods=['POST'])
@login_required
def select_for_display(display_id, media_id):
    display = get_display(display_id)
    media = get_media(media_id)

    if not display or not media:
        flash('Display oder Inhalt nicht gefunden', 'error')
        return redirect(url_for('admin'))

    update_display(display_id, selected_media_id=media_id)
    flash(f'"{media["original_name"]}" wird auf "{display["name"]}" angezeigt', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/display/<int:display_id>/select-newest', methods=['POST'])
@login_required
def select_newest_for_display(display_id):
    display = get_display(display_id)
    if not display:
        flash('Display nicht gefunden', 'error')
        return redirect(url_for('admin'))

    update_display(display_id, selected_media_id=0)
    flash(f'"{display["name"]}" zeigt jetzt den neuesten Inhalt', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/display/<int:display_id>/playlist/add', methods=['POST'])
@login_required
def playlist_add(display_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if not get_display(display_id):
        if is_ajax:
            return jsonify({'ok': False, 'error': 'Display nicht gefunden'}), 404
        flash('Display nicht gefunden', 'error')
        return redirect(url_for('admin'))
    media_id = request.form.get('media_id', type=int)
    duration = max(1, request.form.get('duration', 10, type=int))
    media = get_media(media_id) if media_id else None
    if not media:
        if is_ajax:
            return jsonify({'ok': False, 'error': 'Inhalt nicht gefunden'}), 404
        flash('Inhalt nicht gefunden', 'error')
        return redirect(url_for('admin'))
    new_id = add_playlist_item(display_id, media_id, duration)
    if is_ajax:
        return jsonify({
            'ok': True,
            'id': new_id,
            'original_name': media['original_name'],
            'content_type': media['content_type'],
            'duration': duration,
        })
    flash('Inhalt zur Playlist hinzugefügt', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/display/<int:display_id>/playlist/item/<int:item_id>/remove', methods=['POST'])
@login_required
def playlist_remove(display_id, item_id):
    remove_playlist_item(item_id, display_id)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True})
    return redirect(url_for('admin'))


@app.route('/admin/display/<int:display_id>/playlist/item/<int:item_id>/duration', methods=['POST'])
@login_required
def playlist_update_dur(display_id, item_id):
    duration = request.form.get('duration', type=int)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if not duration or duration < 1:
        if is_ajax:
            return jsonify({'ok': False, 'error': 'Ungültige Dauer'}), 400
        flash('Ungültige Dauer', 'error')
        return redirect(url_for('admin'))
    update_playlist_item_duration(item_id, display_id, duration)
    if is_ajax:
        return jsonify({'ok': True})
    return redirect(url_for('admin'))


@app.route('/admin/display/<int:display_id>/playlist/reorder', methods=['POST'])
@login_required
def playlist_reorder(display_id):
    ordered_ids = request.json.get('order', [])
    reorder_playlist_items(display_id, ordered_ids)
    return jsonify({'ok': True})


@app.route('/admin/display/<int:display_id>/playlist/item/<int:item_id>/move/<direction>', methods=['POST'])
@login_required
def playlist_move_item(display_id, item_id, direction):
    if direction not in ('up', 'down'):
        abort(400)
    move_playlist_item(item_id, display_id, -1 if direction == 'up' else 1)
    return redirect(url_for('admin'))


@app.route('/admin/gallery/create', methods=['POST'])
@login_required
def gallery_create():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Name darf nicht leer sein', 'error')
        return redirect(url_for('admin'))
    add_gallery(name)
    flash(f'Galerie "{name}" erstellt', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/gallery/<int:gallery_id>/upload', methods=['POST'])
@login_required
def gallery_upload(gallery_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    media = get_media(gallery_id)
    if not media or media['content_type'] != 'gallery':
        if is_ajax:
            return jsonify({'ok': False, 'error': 'Galerie nicht gefunden'}), 404
        flash('Galerie nicht gefunden', 'error')
        return redirect(url_for('admin'))

    files = request.files.getlist('files')
    uploaded = []
    for file in files:
        if not file.filename:
            continue
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if ext not in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
            continue
        original_name = secure_filename(file.filename)
        unique_filename = f'{uuid.uuid4()}.{ext}'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        file_size = os.path.getsize(filepath)
        new_id = add_gallery_image(gallery_id, unique_filename, original_name, file_size)
        uploaded.append({'id': new_id, 'filename': unique_filename, 'original_name': original_name})

    if is_ajax:
        return jsonify({'ok': True, 'images': uploaded})
    flash(f'{len(uploaded)} Bild(er) hochgeladen', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/gallery/<int:gallery_id>/image/<int:image_id>/remove', methods=['POST'])
@login_required
def gallery_remove_image(gallery_id, image_id):
    filename = remove_gallery_image(image_id, gallery_id)
    if filename:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': True})
    return redirect(url_for('admin'))


@app.route('/admin/gallery/<int:gallery_id>/image/reorder', methods=['POST'])
@login_required
def gallery_reorder_images(gallery_id):
    ordered_ids = request.json.get('order', [])
    reorder_gallery_images(gallery_id, ordered_ids)
    return jsonify({'ok': True})


@app.route('/admin/display/<int:display_id>/regenerate', methods=['POST'])
@login_required
def regenerate_renders(display_id):
    display = get_display(display_id)
    if not display:
        flash('Display nicht gefunden', 'error')
        return redirect(url_for('admin'))

    errors = []
    count = 0
    for media in get_all_pdf_media():
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], media['filename'])
        if os.path.exists(filepath):
            try:
                render_pdf_for_display(filepath, media['id'], display)
                count += 1
            except RuntimeError as e:
                errors.append(f'{media["original_name"]}: {e}')

    if errors:
        flash(f'{count} PDF(s) gerendert. Fehler: ' + '; '.join(errors), 'error')
    else:
        flash(f'{count} PDF(s) für "{display["name"]}" erfolgreich neu gerendert', 'success')

    return redirect(url_for('admin'))


# --- Content management ---

@app.route('/admin/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        flash('Keine Datei ausgewählt', 'error')
        return redirect(url_for('admin'))

    file = request.files['file']
    if not file.filename:
        flash('Keine Datei ausgewählt', 'error')
        return redirect(url_for('admin'))

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    content_type = ALLOWED_EXTENSIONS.get(ext)
    if not content_type:
        flash('Nicht unterstütztes Dateiformat. Erlaubt: PDF, Bild (JPG/PNG/GIF/WebP), Video (MP4/WebM/MOV)', 'error')
        return redirect(url_for('admin'))

    original_name = secure_filename(file.filename)
    unique_filename = f'{uuid.uuid4()}.{ext}'
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
    file.save(filepath)
    file_size = os.path.getsize(filepath)

    media_id = add_media(content_type, original_name, filename=unique_filename, file_size=file_size)

    # For PDFs: pre-render for all displays
    if content_type == 'pdf':
        errors = []
        for display in get_all_displays():
            try:
                render_pdf_for_display(filepath, media_id, display)
            except RuntimeError as e:
                errors.append(f'{display["name"]}: {e}')

        deleted_count = cleanup_old_media(app.config['UPLOAD_FOLDER'])
        msg = f'"{original_name}" erfolgreich hochgeladen'
        if errors:
            flash(msg + '. Render-Fehler: ' + '; '.join(errors), 'error')
        elif deleted_count > 0:
            flash(f'{msg}. {deleted_count} alte Datei(en) automatisch gelöscht.', 'success')
        else:
            flash(msg, 'success')
    else:
        deleted_count = cleanup_old_media(app.config['UPLOAD_FOLDER'])
        msg = f'"{original_name}" erfolgreich hochgeladen'
        flash(f'{msg}. {deleted_count} alte Datei(en) gelöscht.' if deleted_count else msg, 'success')

    return redirect(url_for('admin'))


@app.route('/admin/url', methods=['POST'])
@login_required
def add_url():
    name = request.form.get('name', '').strip()
    raw_url = request.form.get('url', '').strip()

    if not name or not raw_url:
        flash('Name und URL sind erforderlich', 'error')
        return redirect(url_for('admin'))

    if not raw_url.startswith(('http://', 'https://')):
        flash('URL muss mit http:// oder https:// beginnen', 'error')
        return redirect(url_for('admin'))

    content_type = detect_url_content_type(raw_url)
    final_url = make_youtube_embed(raw_url) if content_type == 'youtube' else raw_url
    scale_to_fit = content_type == 'url' and 'scale_to_fit' in request.form

    add_media(content_type, name, url=final_url, scale_to_fit=scale_to_fit)
    flash(f'"{name}" erfolgreich hinzugefügt', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/media/<int:media_id>/toggle-scale', methods=['POST'])
@login_required
def toggle_scale_to_fit(media_id):
    media = get_media(media_id)
    if not media or media['content_type'] != 'url':
        flash('Inhalt nicht gefunden oder kein Website-Typ', 'error')
        return redirect(url_for('admin'))
    update_media_scale_to_fit(media_id, not media['scale_to_fit'])
    return redirect(url_for('admin'))


@app.route('/admin/media/<int:media_id>/youtube-options', methods=['POST'])
@login_required
def youtube_options(media_id):
    media = get_media(media_id)
    if not media or media['content_type'] != 'youtube':
        flash('Inhalt nicht gefunden oder kein YouTube-Typ', 'error')
        return redirect(url_for('admin'))

    m = re.search(r'/embed/([a-zA-Z0-9_-]+)', media['url'])
    if not m:
        flash('Video-ID konnte nicht ermittelt werden', 'error')
        return redirect(url_for('admin'))

    video_id = m.group(1)
    new_url = make_youtube_embed_with_params(
        video_id,
        controls='controls' in request.form,
        cc='cc' in request.form,
        cc_lang=request.form.get('cc_lang', ''),
        rel='rel' in request.form,
    )
    update_media_url(media_id, new_url)
    flash('YouTube-Einstellungen gespeichert', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/rename/<int:media_id>', methods=['POST'])
@login_required
def rename_media(media_id):
    new_name = request.form.get('new_name', '').strip()
    if not new_name:
        flash('Name darf nicht leer sein', 'error')
        return redirect(url_for('admin'))

    media = get_media(media_id)
    if media and media['content_type'] == 'pdf' and not new_name.lower().endswith('.pdf'):
        new_name += '.pdf'

    update_media_name(media_id, new_name)
    flash('Umbenennung erfolgreich', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/delete/<int:media_id>', methods=['POST'])
@login_required
def delete_media_item(media_id):
    result = delete_media(media_id)
    if not result:
        flash('Inhalt nicht gefunden', 'error')
        return redirect(url_for('admin'))

    # Delete physical file
    if result['filename']:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], result['filename'])
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass

    # Delete render files
    for display_id, render_filename in result['renders']:
        render_path = os.path.join(RENDERS_FOLDER, str(display_id), render_filename)
        if os.path.exists(render_path):
            try:
                os.remove(render_path)
            except OSError:
                pass

    # Delete gallery image files
    for gal_filename in result.get('gallery_images', []):
        gal_path = os.path.join(app.config['UPLOAD_FOLDER'], gal_filename)
        if os.path.exists(gal_path):
            try:
                os.remove(gal_path)
            except OSError:
                pass

    flash('Inhalt erfolgreich gelöscht', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/settings', methods=['POST'])
@login_required
def update_global_settings():
    auto_cleanup_enabled = request.form.get('auto_cleanup_enabled', '').strip()
    auto_cleanup_days = request.form.get('auto_cleanup_days', type=int)

    errors = []
    if auto_cleanup_enabled not in ('true', 'false'):
        errors.append('Ungültige Auto-Cleanup-Einstellung')
    if not auto_cleanup_days or auto_cleanup_days < 1:
        errors.append('Ungültige Aufbewahrungsdauer')

    if errors:
        for e in errors:
            flash(e, 'error')
    else:
        set_setting('auto_cleanup_enabled', auto_cleanup_enabled)
        set_setting('auto_cleanup_days', auto_cleanup_days)
        flash('Einstellungen gespeichert', 'success')

    return redirect(url_for('admin'))


@app.route('/admin/cleanup', methods=['POST'])
@login_required
def manual_cleanup():
    deleted_count = cleanup_old_media(app.config['UPLOAD_FOLDER'])
    if deleted_count > 0:
        flash(f'{deleted_count} alte Datei(en) gelöscht', 'success')
    else:
        flash('Keine alten Dateien zum Löschen gefunden', 'info')
    return redirect(url_for('admin'))


if __name__ == '__main__':
    from waitress import serve
    print(f'Starting Kundenstopper on {config.host}:{config.port}')
    print(f'Admin: http://{config.host}:{config.port}/admin')
    for d in get_all_displays():
        print(f'Display "{d["name"]}": http://{config.host}:{config.port}/display/{d["slug"]}')
    serve(app, host=config.host, port=config.port)
