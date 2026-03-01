"""
Server locale per il sito IISS Giudici Saetta e Livatino.
Serve i file statici e gestisce il salvataggio delle notizie e pagine.
Avviare con: python server.py
"""

import base64
import ftplib
import hashlib
import http.server
import io
import json
import os
import re
import secrets
import webbrowser
import socketserver
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from glob import glob
from http.cookies import SimpleCookie

PORT = 3000
SITE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else os.getcwd()
NOTIZIE_PATH = os.path.join(SITE_DIR, "data", "notizie.json")
ORGANIGRAMMA_PATH = os.path.join(SITE_DIR, "data", "organigramma.json")
PAGINE_DIR = os.path.join(SITE_DIR, "pagine")
USERS_PATH = os.path.join(SITE_DIR, "data", "users.json")
SYNC_CONFIG_PATH = os.path.join(SITE_DIR, "data", "sync_config.json")
GITHUB_CONFIG_PATH_OLD = os.path.join(SITE_DIR, "data", "github_config.json")

MAX_BACKUPS = 5
SESSION_EXPIRY_HOURS = 8
RUOLI = ['editor', 'admin']

# Sessioni in memoria
sessions = {}  # { token: { username, ruolo, expires } }

# Upload file
UPLOAD_BASE = os.path.join(SITE_DIR, "docs", "pdf")
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'odt', 'rtf', 'txt',
    'xls', 'xlsx', 'ods', 'csv',
    'ppt', 'pptx', 'odp',
    'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg',
    'zip', 'rar', '7z'
}


def sanitize_filename(filename):
    """Sanitizza un nome file: rimuove caratteri speciali, spazi → underscore."""
    # Estrai nome e estensione
    name, ext = os.path.splitext(filename)
    # Rimuovi caratteri non alfanumerici (tranne trattini e underscore)
    name = re.sub(r'[^\w\-]', '_', name, flags=re.UNICODE)
    # Collassa underscore multipli
    name = re.sub(r'_+', '_', name).strip('_')
    # Limita lunghezza
    if len(name) > 100:
        name = name[:100]
    return name + ext.lower() if name else 'file' + ext.lower()


def estrai_contenuto_pagina(html):
    """Estrae titolo, sottotitolo e contenuto editabile da una pagina HTML."""
    # Titolo da <h1> dentro page-header
    h1_match = re.search(r'<section class="page-header">\s*<div class="container">.*?<h1>(.*?)</h1>', html, re.DOTALL)
    titolo = h1_match.group(1).strip() if h1_match else ""

    # Sottotitolo da <p> dentro page-header (dopo h1)
    sottotitolo = ""
    if h1_match:
        after_h1 = html[h1_match.end():]
        p_match = re.search(r'<p>(.*?)</p>\s*</div>\s*</section>', after_h1, re.DOTALL)
        if p_match:
            sottotitolo = p_match.group(1).strip()

    # Contenuto: innerHTML di <section class="page-content"><div class="container">
    content_match = re.search(
        r'<section class="page-content">\s*<div class="container">\s*(.*?)\s*</div>\s*</section>',
        html, re.DOTALL
    )
    contenuto = content_match.group(1).strip() if content_match else ""

    return titolo, sottotitolo, contenuto


def sostituisci_contenuto_pagina(html, titolo, sottotitolo, contenuto):
    """Sostituisce titolo, sottotitolo e contenuto in una pagina HTML."""
    # Sostituisci h1
    html = re.sub(
        r'(<section class="page-header">\s*<div class="container">.*?<h1>)(.*?)(</h1>)',
        lambda m: m.group(1) + titolo + m.group(3),
        html, count=1, flags=re.DOTALL
    )

    # Sostituisci sottotitolo (p dopo h1 dentro page-header)
    def replace_subtitle(m):
        before = m.group(0)
        return re.sub(
            r'(<h1>.*?</h1>\s*<p>)(.*?)(</p>\s*</div>\s*</section>)',
            lambda sm: sm.group(1) + sottotitolo + sm.group(3),
            before, count=1, flags=re.DOTALL
        )

    html = re.sub(
        r'<section class="page-header">.*?</section>',
        replace_subtitle,
        html, count=1, flags=re.DOTALL
    )

    # Sostituisci contenuto page-content
    html = re.sub(
        r'(<section class="page-content">\s*<div class="container">)\s*.*?\s*(</div>\s*</section>)',
        lambda m: m.group(1) + "\n\n    " + contenuto + "\n\n  " + m.group(2),
        html, count=1, flags=re.DOTALL
    )

    return html


def gestisci_backup(filepath):
    """Crea un backup timestamped e mantiene solo gli ultimi MAX_BACKUPS."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{filepath}.backup.{timestamp}"
    with open(filepath, "r", encoding="utf-8") as f:
        contenuto = f.read()
    with open(backup_name, "w", encoding="utf-8") as f:
        f.write(contenuto)

    # Rimuovi backup vecchi (mantieni solo gli ultimi MAX_BACKUPS)
    pattern = filepath + ".backup.*"
    backups = sorted(glob(pattern))
    while len(backups) > MAX_BACKUPS:
        os.remove(backups.pop(0))

    return os.path.basename(backup_name)


def hash_password(password, salt=None):
    """Hash password con PBKDF2-SHA256, 100k iterazioni."""
    if salt is None:
        salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return pw_hash.hex(), salt


def verify_password(password, stored_hash, salt):
    """Verifica password con confronto constant-time."""
    pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return secrets.compare_digest(pw_hash.hex(), stored_hash)


def load_users():
    """Carica utenti da users.json."""
    if not os.path.exists(USERS_PATH):
        return []
    with open(USERS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_users(users):
    """Salva utenti su users.json."""
    os.makedirs(os.path.dirname(USERS_PATH), exist_ok=True)
    with open(USERS_PATH, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def find_user(users, username):
    """Trova utente per username. Ritorna (index, user_dict) o (-1, None)."""
    for i, u in enumerate(users):
        if u['username'] == username:
            return i, u
    return -1, None


def init_users():
    """Crea admin predefinito se users.json non esiste."""
    if os.path.exists(USERS_PATH):
        return False
    pw_hash, salt = hash_password('admin1')
    users = [{
        'username': 'admin',
        'password_hash': pw_hash,
        'salt': salt,
        'ruolo': 'admin',
        'creato': datetime.now().isoformat(timespec='seconds')
    }]
    save_users(users)
    return True


def load_sync_config():
    """Carica configurazione sync. Migra da vecchio github_config.json se necessario."""
    # Migrazione: se esiste il vecchio file ma non il nuovo, migra
    if not os.path.exists(SYNC_CONFIG_PATH) and os.path.exists(GITHUB_CONFIG_PATH_OLD):
        try:
            with open(GITHUB_CONFIG_PATH_OLD, 'r', encoding='utf-8') as f:
                old = json.load(f)
            new_config = {
                "metodo": "github" if old.get('token', '').strip() else "nessuno",
                "github": {
                    "token": old.get('token', ''),
                    "owner": old.get('owner', ''),
                    "repo": old.get('repo', ''),
                    "branch": old.get('branch', 'main')
                },
                "ftp": {
                    "host": "", "porta": 21, "username": "", "password": "",
                    "percorso_remoto": "/public_html", "tls": True
                }
            }
            os.makedirs(os.path.dirname(SYNC_CONFIG_PATH), exist_ok=True)
            with open(SYNC_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(new_config, f, ensure_ascii=False, indent=2)
            print('[SYNC] Migrata configurazione da github_config.json a sync_config.json')
            return new_config
        except Exception:
            pass

    if not os.path.exists(SYNC_CONFIG_PATH):
        return None
    try:
        with open(SYNC_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def save_sync_config(config):
    """Salva configurazione sync su disco."""
    os.makedirs(os.path.dirname(SYNC_CONFIG_PATH), exist_ok=True)
    with open(SYNC_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def sync_file(relative_path, file_bytes=None):
    """Sincronizza un file online in base alla configurazione.

    Args:
        relative_path: percorso relativo alla root del sito (es. 'data/notizie.json')
        file_bytes: bytes del file (se None, legge dal disco)

    Returns:
        'ok' se sincronizzato, 'skipped' se config mancante/disattivato, oppure stringa errore
    """
    config = load_sync_config()
    if not config:
        return 'skipped'

    metodo = config.get('metodo', 'nessuno')
    if metodo == 'nessuno':
        return 'skipped'

    # Leggi il file se non fornito come bytes
    if file_bytes is None:
        filepath = os.path.join(SITE_DIR, relative_path)
        try:
            with open(filepath, 'rb') as f:
                file_bytes = f.read()
        except Exception as e:
            return f'Errore lettura file: {e}'

    if metodo == 'github':
        return _sync_github(config.get('github', {}), relative_path, file_bytes)
    elif metodo == 'ftp':
        return _sync_ftp(config.get('ftp', {}), relative_path, file_bytes)
    else:
        return 'skipped'


def _sync_github(gh, relative_path, file_bytes):
    """Sincronizza un file su GitHub via Contents API."""
    token = gh.get('token', '').strip()
    owner = gh.get('owner', '').strip()
    repo = gh.get('repo', '').strip()
    branch = gh.get('branch', 'main').strip()

    if not token or not owner or not repo:
        return 'skipped'

    api_path = relative_path.replace('\\', '/')
    api_url = f'https://api.github.com/repos/{owner}/{repo}/contents/{api_path}'
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'IISS-SitoAdmin/1.0'
    }

    try:
        sha = None
        req = urllib.request.Request(api_url, headers=headers, method='GET')
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                sha = data.get('sha')
        except urllib.error.HTTPError as e:
            if e.code != 404:
                return f'Errore GitHub GET: {e.code} {e.reason}'

        content_b64 = base64.b64encode(file_bytes).decode('ascii')
        put_data = {
            'message': f'Aggiorna {api_path} da pannello admin',
            'content': content_b64,
            'branch': branch
        }
        if sha:
            put_data['sha'] = sha

        put_body = json.dumps(put_data).encode('utf-8')
        req = urllib.request.Request(api_url, data=put_body, headers={
            **headers,
            'Content-Type': 'application/json'
        }, method='PUT')
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status in (200, 201):
                print(f'[SYNC] Sincronizzato su GitHub: {api_path}')
                return 'ok'
            else:
                return f'Errore GitHub PUT: {resp.status}'

    except urllib.error.HTTPError as e:
        return f'Errore GitHub: {e.code} {e.reason}'
    except Exception as e:
        return f'Errore sync GitHub: {e}'


def _sync_ftp(ftp_cfg, relative_path, file_bytes):
    """Sincronizza un file via FTP/FTPS."""
    host = ftp_cfg.get('host', '').strip()
    porta = int(ftp_cfg.get('porta', 21))
    username = ftp_cfg.get('username', '').strip()
    password = ftp_cfg.get('password', '')
    percorso_remoto = ftp_cfg.get('percorso_remoto', '/public_html').strip()
    use_tls = ftp_cfg.get('tls', True)

    if not host or not username:
        return 'skipped'

    ftp = None
    try:
        if use_tls:
            ftp = ftplib.FTP_TLS(timeout=15)
        else:
            ftp = ftplib.FTP(timeout=15)

        ftp.connect(host, porta)
        ftp.login(username, password)

        if use_tls:
            ftp.prot_p()

        # Naviga al percorso remoto base
        if percorso_remoto:
            ftp.cwd(percorso_remoto)

        # Crea directory intermedie e naviga
        remote_path = relative_path.replace('\\', '/')
        parts = remote_path.split('/')
        filename = parts[-1]
        dirs = parts[:-1]

        for d in dirs:
            try:
                ftp.cwd(d)
            except ftplib.error_perm:
                ftp.mkd(d)
                ftp.cwd(d)

        # Upload file
        ftp.storbinary(f'STOR {filename}', io.BytesIO(file_bytes))

        print(f'[SYNC] Sincronizzato via FTP: {remote_path}')
        return 'ok'

    except Exception as e:
        return f'Errore FTP: {e}'
    finally:
        if ftp:
            try:
                ftp.quit()
            except Exception:
                try:
                    ftp.close()
                except Exception:
                    pass


class SitoHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SITE_DIR, **kwargs)

    def get_current_user(self):
        """Legge cookie session_token, valida sessione, ritorna user dict o None."""
        cookie_header = self.headers.get('Cookie', '')
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        morsel = cookie.get('session_token')
        if not morsel:
            return None
        token = morsel.value
        session = sessions.get(token)
        if not session:
            return None
        if datetime.now() > session['expires']:
            del sessions[token]
            return None
        return {'username': session['username'], 'ruolo': session['ruolo']}

    def require_auth(self, ruolo_minimo=None):
        """Controlla auth + ruolo. Invia 401/403 se fallisce. Ritorna user o None."""
        user = self.get_current_user()
        if not user:
            self.send_error_json(401, "Non autenticato")
            return None
        if ruolo_minimo:
            livello_richiesto = RUOLI.index(ruolo_minimo)
            livello_utente = RUOLI.index(user['ruolo']) if user['ruolo'] in RUOLI else -1
            if livello_utente < livello_richiesto:
                self.send_error_json(403, "Permessi insufficienti")
                return None
        return user

    def send_json_with_cookie(self, data, cookie_str):
        """Risposta JSON con Set-Cookie."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Set-Cookie", cookie_str)
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def read_json_body(self):
        """Legge e parsa il body JSON della richiesta."""
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        return json.loads(body.decode("utf-8"))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/lista-pagine":
            if not self.require_auth('editor'):
                return
            self.handle_lista_pagine()
        elif path == "/api/pagina":
            if not self.require_auth('editor'):
                return
            params = urllib.parse.parse_qs(parsed.query)
            filename = params.get("file", [None])[0]
            self.handle_get_pagina(filename)
        elif path == "/api/utente-corrente":
            self.handle_utente_corrente()
        elif path == "/api/lista-utenti":
            if not self.require_auth('admin'):
                return
            self.handle_lista_utenti()
        elif path == "/api/organigramma":
            if not self.require_auth('editor'):
                return
            self.handle_get_organigramma()
        elif path == "/api/sync-config":
            if not self.require_auth('admin'):
                return
            self.handle_get_sync_config()
        else:
            # File statici
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/login":
            self.handle_login()
        elif self.path == "/api/logout":
            self.handle_logout()
        elif self.path == "/api/cambia-password":
            if not self.require_auth():
                return
            self.handle_cambia_password()
        elif self.path == "/api/crea-utente":
            if not self.require_auth('admin'):
                return
            self.handle_crea_utente()
        elif self.path == "/api/elimina-utente":
            if not self.require_auth('admin'):
                return
            self.handle_elimina_utente()
        elif self.path == "/api/cambia-ruolo":
            if not self.require_auth('admin'):
                return
            self.handle_cambia_ruolo()
        elif self.path == "/api/salva-notizie":
            if not self.require_auth('editor'):
                return
            self.handle_salva_notizie()
        elif self.path == "/api/salva-pagina":
            if not self.require_auth('editor'):
                return
            self.handle_salva_pagina()
        elif self.path == "/api/upload-file":
            if not self.require_auth('editor'):
                return
            self.handle_upload_file()
        elif self.path == "/api/anteprima":
            if not self.require_auth('editor'):
                return
            self.handle_anteprima()
        elif self.path == "/api/salva-organigramma":
            if not self.require_auth('editor'):
                return
            self.handle_salva_organigramma()
        elif self.path == "/api/sync-config":
            if not self.require_auth('admin'):
                return
            self.handle_post_sync_config()
        elif self.path == "/api/sync-test":
            if not self.require_auth('admin'):
                return
            self.handle_sync_test()
        else:
            self.send_error(404, "Endpoint non trovato")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # --- API: Lista pagine ---
    def handle_lista_pagine(self):
        try:
            pagine = []
            for filepath in sorted(glob(os.path.join(PAGINE_DIR, "*.html"))):
                filename = os.path.basename(filepath)
                with open(filepath, "r", encoding="utf-8") as f:
                    html = f.read()
                # Estrai titolo dal tag <title>
                title_match = re.search(r'<title>(.*?)(?:\s*-\s*IISS.*?)?</title>', html)
                titolo = title_match.group(1).strip() if title_match else filename
                pagine.append({"file": filename, "titolo": titolo})

            self.send_json({"ok": True, "pagine": pagine})
            print(f"[OK] Lista pagine: {len(pagine)} pagine trovate")
        except Exception as e:
            self.send_error_json(500, f"Errore lista pagine: {e}")

    # --- API: Leggi pagina ---
    def handle_get_pagina(self, filename):
        if not filename:
            self.send_error_json(400, "Parametro 'file' mancante")
            return

        # Validazione filename (solo caratteri sicuri)
        if not re.match(r'^[a-z0-9-]+\.html$', filename):
            self.send_error_json(400, "Nome file non valido")
            return

        filepath = os.path.join(PAGINE_DIR, filename)
        if not os.path.exists(filepath):
            self.send_error_json(404, f"Pagina '{filename}' non trovata")
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                html = f.read()

            titolo, sottotitolo, contenuto = estrai_contenuto_pagina(html)
            self.send_json({
                "ok": True,
                "file": filename,
                "titolo": titolo,
                "sottotitolo": sottotitolo,
                "contenuto": contenuto
            })
            print(f"[OK] Pagina caricata: {filename}")
        except Exception as e:
            self.send_error_json(500, f"Errore lettura pagina: {e}")

    # --- API: Salva pagina ---
    def handle_salva_pagina(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body.decode("utf-8"))

            filename = data.get("file", "")
            titolo = data.get("titolo", "")
            sottotitolo = data.get("sottotitolo", "")
            contenuto = data.get("contenuto", "")

            # Validazione
            if not re.match(r'^[a-z0-9-]+\.html$', filename):
                self.send_error_json(400, "Nome file non valido")
                return

            filepath = os.path.join(PAGINE_DIR, filename)
            if not os.path.exists(filepath):
                self.send_error_json(404, f"Pagina '{filename}' non trovata")
                return

            if not titolo.strip():
                self.send_error_json(400, "Il titolo non può essere vuoto")
                return

            # Backup
            backup_name = gestisci_backup(filepath)

            # Leggi, sostituisci, salva
            with open(filepath, "r", encoding="utf-8") as f:
                html = f.read()

            html_nuovo = sostituisci_contenuto_pagina(html, titolo, sottotitolo, contenuto)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html_nuovo)

            # Sync su GitHub
            sync_result = sync_file(f"pagine/{filename}")

            messaggio = f"Pagina '{titolo}' salvata con successo"
            if sync_result == 'ok':
                messaggio += " — Pubblicato online"
            self.send_json({
                "ok": True,
                "messaggio": messaggio,
                "backup": backup_name,
                "sync": sync_result
            })
            print(f"[OK] Pagina salvata: {filename} (backup: {backup_name}, sync: {sync_result})")

        except json.JSONDecodeError:
            self.send_error_json(400, "JSON non valido")
        except ValueError as e:
            self.send_error_json(400, str(e))
        except Exception as e:
            self.send_error_json(500, f"Errore salvataggio pagina: {e}")

    # --- API: Upload file ---
    def handle_upload_file(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body.decode("utf-8"))

            file_data = data.get("file_data", "")
            filename = data.get("filename", "")
            cartella = data.get("cartella", "")

            # Valida cartella
            if not re.match(r'^[a-z0-9-]+$', cartella):
                self.send_error_json(400, "Nome cartella non valido (solo lettere minuscole, numeri, trattini)")
                return

            # Sanitizza filename
            filename = sanitize_filename(filename)
            if not filename:
                self.send_error_json(400, "Nome file non valido")
                return

            # Valida estensione
            ext = os.path.splitext(filename)[1].lstrip('.').lower()
            if ext not in ALLOWED_EXTENSIONS:
                self.send_error_json(400, f"Tipo file '.{ext}' non consentito. Tipi ammessi: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
                return

            # Decodifica base64 (rimuovi eventuale prefisso data:...)
            if ',' in file_data:
                file_data = file_data.split(',', 1)[1]
            try:
                file_bytes = base64.b64decode(file_data)
            except Exception:
                self.send_error_json(400, "Dati file non validi (base64 corrotto)")
                return

            # Verifica dimensione
            if len(file_bytes) > MAX_FILE_SIZE:
                size_mb = len(file_bytes) / (1024 * 1024)
                self.send_error_json(400, f"File troppo grande ({size_mb:.1f}MB). Massimo consentito: 10MB")
                return

            # Crea directory
            upload_dir = os.path.join(UPLOAD_BASE, cartella)
            os.makedirs(upload_dir, exist_ok=True)

            # Gestisci nomi duplicati
            final_name = filename
            base_name, file_ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(os.path.join(upload_dir, final_name)):
                final_name = f"{base_name}_{counter}{file_ext}"
                counter += 1

            # Salva file
            filepath = os.path.join(upload_dir, final_name)
            with open(filepath, "wb") as f:
                f.write(file_bytes)

            # Sync su GitHub (passa i bytes gia' decodificati)
            sync_path = f"docs/pdf/{cartella}/{final_name}"
            sync_result = sync_file(sync_path, file_bytes)

            # URL relativo a pagine/ (per snippet nell'editor pagine)
            url_pagine = f"../docs/pdf/{cartella}/{final_name}"
            # URL relativo a root (per notizie e link generici)
            url_root = f"docs/pdf/{cartella}/{final_name}"

            self.send_json({
                "ok": True,
                "filename": final_name,
                "url": url_pagine,
                "url_root": url_root,
                "size": len(file_bytes),
                "sync": sync_result
            })
            print(f"[OK] File caricato: {filepath} ({len(file_bytes)} bytes, sync: {sync_result})")

        except json.JSONDecodeError:
            self.send_error_json(400, "JSON non valido")
        except Exception as e:
            self.send_error_json(500, f"Errore upload: {e}")

    # --- API: Salva notizie (esistente) ---
    def handle_salva_notizie(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            notizie = json.loads(body.decode("utf-8"))

            if not isinstance(notizie, list):
                raise ValueError("Il formato deve essere una lista di notizie")

            for i, n in enumerate(notizie):
                if not n.get("titolo") or not n.get("categoria"):
                    raise ValueError(f"Notizia {i+1}: titolo e categoria sono obbligatori")

            # Backup del file esistente
            if os.path.exists(NOTIZIE_PATH):
                backup = NOTIZIE_PATH + ".backup"
                with open(NOTIZIE_PATH, "r", encoding="utf-8") as f:
                    with open(backup, "w", encoding="utf-8") as fb:
                        fb.write(f.read())

            os.makedirs(os.path.dirname(NOTIZIE_PATH), exist_ok=True)
            with open(NOTIZIE_PATH, "w", encoding="utf-8") as f:
                json.dump(notizie, f, ensure_ascii=False, indent=2)

            # Sync su GitHub
            sync_result = sync_file("data/notizie.json")

            messaggio = f"Salvate {len(notizie)} notizie"
            if sync_result == 'ok':
                messaggio += " — Pubblicato online"
            self.send_json({"ok": True, "messaggio": messaggio, "sync": sync_result})
            print(f"[OK] Salvate {len(notizie)} notizie in {NOTIZIE_PATH} (sync: {sync_result})")

        except json.JSONDecodeError:
            self.send_error_json(400, "JSON non valido")
        except ValueError as e:
            self.send_error_json(400, str(e))
        except Exception as e:
            self.send_error_json(500, f"Errore interno: {e}")

    # --- API: Anteprima pagina (senza salvare) ---
    def handle_anteprima(self):
        try:
            data = self.read_json_body()
            filename = data.get("file", "")
            titolo = data.get("titolo", "")
            sottotitolo = data.get("sottotitolo", "")
            contenuto = data.get("contenuto", "")

            if not re.match(r'^[a-z0-9-]+\.html$', filename):
                self.send_error_json(400, "Nome file non valido")
                return

            filepath = os.path.join(PAGINE_DIR, filename)
            if not os.path.exists(filepath):
                self.send_error_json(404, f"Pagina '{filename}' non trovata")
                return

            with open(filepath, "r", encoding="utf-8") as f:
                html = f.read()

            html_preview = sostituisci_contenuto_pagina(html, titolo, sottotitolo, contenuto)

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html_preview.encode("utf-8"))
            print(f"[OK] Anteprima generata: {filename}")

        except json.JSONDecodeError:
            self.send_error_json(400, "JSON non valido")
        except Exception as e:
            self.send_error_json(500, f"Errore anteprima: {e}")

    # --- API: Login ---
    def handle_login(self):
        try:
            data = self.read_json_body()
            username = data.get("username", "").strip().lower()
            password = data.get("password", "")

            if not username or not password:
                self.send_error_json(400, "Username e password obbligatori")
                return

            users = load_users()
            _, user = find_user(users, username)
            if not user or not verify_password(password, user['password_hash'], user['salt']):
                self.send_error_json(401, "Credenziali non valide")
                return

            token = secrets.token_urlsafe(32)
            sessions[token] = {
                'username': user['username'],
                'ruolo': user['ruolo'],
                'expires': datetime.now() + timedelta(hours=SESSION_EXPIRY_HOURS)
            }

            cookie = f"session_token={token}; HttpOnly; SameSite=Strict; Path=/"
            self.send_json_with_cookie({
                "ok": True,
                "username": user['username'],
                "ruolo": user['ruolo']
            }, cookie)
            print(f"[OK] Login: {user['username']} ({user['ruolo']})")

        except json.JSONDecodeError:
            self.send_error_json(400, "JSON non valido")
        except Exception as e:
            self.send_error_json(500, f"Errore login: {e}")

    # --- API: Logout ---
    def handle_logout(self):
        cookie_header = self.headers.get('Cookie', '')
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        morsel = cookie.get('session_token')
        if morsel and morsel.value in sessions:
            del sessions[morsel.value]

        expire_cookie = "session_token=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
        self.send_json_with_cookie({"ok": True, "messaggio": "Logout effettuato"}, expire_cookie)

    # --- API: Utente corrente ---
    def handle_utente_corrente(self):
        user = self.get_current_user()
        if not user:
            self.send_error_json(401, "Non autenticato")
            return
        self.send_json({"ok": True, "username": user['username'], "ruolo": user['ruolo']})

    # --- API: Lista utenti ---
    def handle_lista_utenti(self):
        users = load_users()
        lista = [{"username": u['username'], "ruolo": u['ruolo'], "creato": u.get('creato', '')} for u in users]
        self.send_json({"ok": True, "utenti": lista})

    # --- API: Crea utente ---
    def handle_crea_utente(self):
        try:
            data = self.read_json_body()
            username = data.get("username", "").strip().lower()
            password = data.get("password", "")
            ruolo = data.get("ruolo", "editor")

            if not re.match(r'^[a-z0-9._-]{3,30}$', username):
                self.send_error_json(400, "Username non valido (3-30 caratteri, solo a-z 0-9 . _ -)")
                return
            if len(password) < 6:
                self.send_error_json(400, "Password troppo corta (minimo 6 caratteri)")
                return
            if ruolo not in RUOLI:
                self.send_error_json(400, f"Ruolo non valido. Ruoli ammessi: {', '.join(RUOLI)}")
                return

            users = load_users()
            _, existing = find_user(users, username)
            if existing:
                self.send_error_json(400, f"Username '{username}' già in uso")
                return

            pw_hash, salt = hash_password(password)
            users.append({
                'username': username,
                'password_hash': pw_hash,
                'salt': salt,
                'ruolo': ruolo,
                'creato': datetime.now().isoformat(timespec='seconds')
            })
            save_users(users)
            self.send_json({"ok": True, "messaggio": f"Utente '{username}' creato con ruolo {ruolo}"})
            print(f"[OK] Utente creato: {username} ({ruolo})")

        except json.JSONDecodeError:
            self.send_error_json(400, "JSON non valido")
        except Exception as e:
            self.send_error_json(500, f"Errore creazione utente: {e}")

    # --- API: Elimina utente ---
    def handle_elimina_utente(self):
        try:
            data = self.read_json_body()
            username = data.get("username", "").strip().lower()
            current_user = self.get_current_user()

            if not username:
                self.send_error_json(400, "Username obbligatorio")
                return
            if username == current_user['username']:
                self.send_error_json(400, "Non puoi eliminare te stesso")
                return

            users = load_users()
            idx, user = find_user(users, username)
            if idx == -1:
                self.send_error_json(404, f"Utente '{username}' non trovato")
                return

            # Controlla che rimanga almeno un admin
            if user['ruolo'] == 'admin':
                admin_count = sum(1 for u in users if u['ruolo'] == 'admin')
                if admin_count <= 1:
                    self.send_error_json(400, "Impossibile eliminare l'ultimo admin")
                    return

            users.pop(idx)
            save_users(users)
            # Rimuovi sessioni dell'utente eliminato
            tokens_to_remove = [t for t, s in sessions.items() if s['username'] == username]
            for t in tokens_to_remove:
                del sessions[t]

            self.send_json({"ok": True, "messaggio": f"Utente '{username}' eliminato"})
            print(f"[OK] Utente eliminato: {username}")

        except json.JSONDecodeError:
            self.send_error_json(400, "JSON non valido")
        except Exception as e:
            self.send_error_json(500, f"Errore eliminazione utente: {e}")

    # --- API: Cambia password ---
    def handle_cambia_password(self):
        try:
            data = self.read_json_body()
            password_attuale = data.get("password_attuale", "")
            password_nuova = data.get("password_nuova", "")
            current_user = self.get_current_user()

            if not password_attuale or not password_nuova:
                self.send_error_json(400, "Password attuale e nuova obbligatorie")
                return
            if len(password_nuova) < 6:
                self.send_error_json(400, "Nuova password troppo corta (minimo 6 caratteri)")
                return

            users = load_users()
            idx, user = find_user(users, current_user['username'])
            if idx == -1:
                self.send_error_json(404, "Utente non trovato")
                return

            if not verify_password(password_attuale, user['password_hash'], user['salt']):
                self.send_error_json(401, "Password attuale non corretta")
                return

            pw_hash, salt = hash_password(password_nuova)
            users[idx]['password_hash'] = pw_hash
            users[idx]['salt'] = salt
            save_users(users)
            self.send_json({"ok": True, "messaggio": "Password cambiata con successo"})
            print(f"[OK] Password cambiata: {current_user['username']}")

        except json.JSONDecodeError:
            self.send_error_json(400, "JSON non valido")
        except Exception as e:
            self.send_error_json(500, f"Errore cambio password: {e}")

    # --- API: Cambia ruolo ---
    def handle_cambia_ruolo(self):
        try:
            data = self.read_json_body()
            username = data.get("username", "").strip().lower()
            nuovo_ruolo = data.get("ruolo", "")
            current_user = self.get_current_user()

            if not username or not nuovo_ruolo:
                self.send_error_json(400, "Username e ruolo obbligatori")
                return
            if nuovo_ruolo not in RUOLI:
                self.send_error_json(400, f"Ruolo non valido. Ruoli ammessi: {', '.join(RUOLI)}")
                return

            users = load_users()
            idx, user = find_user(users, username)
            if idx == -1:
                self.send_error_json(404, f"Utente '{username}' non trovato")
                return

            # Controlla che rimanga almeno un admin
            if user['ruolo'] == 'admin' and nuovo_ruolo != 'admin':
                admin_count = sum(1 for u in users if u['ruolo'] == 'admin')
                if admin_count <= 1:
                    self.send_error_json(400, "Impossibile declassare l'ultimo admin")
                    return

            users[idx]['ruolo'] = nuovo_ruolo
            save_users(users)

            # Aggiorna sessioni attive dell'utente
            for s in sessions.values():
                if s['username'] == username:
                    s['ruolo'] = nuovo_ruolo

            self.send_json({"ok": True, "messaggio": f"Ruolo di '{username}' cambiato in {nuovo_ruolo}"})
            print(f"[OK] Ruolo cambiato: {username} -> {nuovo_ruolo}")

        except json.JSONDecodeError:
            self.send_error_json(400, "JSON non valido")
        except Exception as e:
            self.send_error_json(500, f"Errore cambio ruolo: {e}")

    # --- API: Organigramma ---
    def handle_get_organigramma(self):
        try:
            if not os.path.exists(ORGANIGRAMMA_PATH):
                self.send_json({"ok": True, "anno_scolastico": "", "sezioni": []})
                return
            with open(ORGANIGRAMMA_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.send_json({"ok": True, **data})
            print(f"[OK] Organigramma caricato")
        except Exception as e:
            self.send_error_json(500, f"Errore lettura organigramma: {e}")

    def handle_salva_organigramma(self):
        try:
            data = self.read_json_body()
            anno = data.get("anno_scolastico", "").strip()
            sezioni = data.get("sezioni", [])

            if not anno:
                self.send_error_json(400, "Anno scolastico obbligatorio")
                return
            if not isinstance(sezioni, list):
                self.send_error_json(400, "Formato sezioni non valido")
                return

            organigramma = {"anno_scolastico": anno, "sezioni": sezioni}

            # Backup del file esistente
            if os.path.exists(ORGANIGRAMMA_PATH):
                backup_name = gestisci_backup(ORGANIGRAMMA_PATH)
            else:
                backup_name = None

            os.makedirs(os.path.dirname(ORGANIGRAMMA_PATH), exist_ok=True)
            with open(ORGANIGRAMMA_PATH, "w", encoding="utf-8") as f:
                json.dump(organigramma, f, ensure_ascii=False, indent=2)

            # Sync su GitHub
            sync_result = sync_file("data/organigramma.json")

            msg = "Organigramma pubblicato con successo"
            if sync_result == 'ok':
                msg += " — Pubblicato online"
            self.send_json({"ok": True, "messaggio": msg, "backup": backup_name, "sync": sync_result})
            print(f"[OK] Organigramma salvato ({len(sezioni)} sezioni, backup: {backup_name}, sync: {sync_result})")

        except json.JSONDecodeError:
            self.send_error_json(400, "JSON non valido")
        except Exception as e:
            self.send_error_json(500, f"Errore salvataggio organigramma: {e}")

    # --- API: Sync Config ---
    def handle_get_sync_config(self):
        config = load_sync_config()
        if not config:
            config = {
                "metodo": "nessuno",
                "github": {"token": "", "owner": "", "repo": "", "branch": "main"},
                "ftp": {"host": "", "porta": 21, "username": "", "password": "",
                        "percorso_remoto": "/public_html", "tls": True}
            }

        # Mascera password
        safe = json.loads(json.dumps(config))
        if safe.get('github', {}).get('token', ''):
            safe['github']['token'] = '\u25cf\u25cf\u25cf\u25cf\u25cf\u25cf'
        if safe.get('ftp', {}).get('password', ''):
            safe['ftp']['password'] = '\u25cf\u25cf\u25cf\u25cf\u25cf\u25cf'
        self.send_json({"ok": True, **safe})

    def handle_post_sync_config(self):
        try:
            data = self.read_json_body()
            metodo = data.get('metodo', 'nessuno')
            if metodo not in ('nessuno', 'github', 'ftp'):
                self.send_error_json(400, "Metodo non valido")
                return

            # Carica config esistente per preservare password mascherate
            existing = load_sync_config() or {}

            gh = data.get('github', {})
            ftp_data = data.get('ftp', {})

            # Se token mascherato, mantieni quello esistente
            mask = '\u25cf\u25cf\u25cf\u25cf\u25cf\u25cf'
            if gh.get('token', '') == mask:
                gh['token'] = existing.get('github', {}).get('token', '')
            if ftp_data.get('password', '') == mask:
                ftp_data['password'] = existing.get('ftp', {}).get('password', '')

            new_config = {
                "metodo": metodo,
                "github": {
                    "token": gh.get('token', ''),
                    "owner": gh.get('owner', ''),
                    "repo": gh.get('repo', ''),
                    "branch": gh.get('branch', 'main')
                },
                "ftp": {
                    "host": ftp_data.get('host', ''),
                    "porta": int(ftp_data.get('porta', 21)),
                    "username": ftp_data.get('username', ''),
                    "password": ftp_data.get('password', ''),
                    "percorso_remoto": ftp_data.get('percorso_remoto', '/public_html'),
                    "tls": bool(ftp_data.get('tls', True))
                }
            }

            save_sync_config(new_config)
            self.send_json({"ok": True, "messaggio": "Configurazione salvata"})
            print(f"[OK] Configurazione sync salvata: metodo={metodo}")

        except json.JSONDecodeError:
            self.send_error_json(400, "JSON non valido")
        except Exception as e:
            self.send_error_json(500, f"Errore salvataggio configurazione: {e}")

    def handle_sync_test(self):
        try:
            data = self.read_json_body()
            metodo = data.get('metodo', 'nessuno')

            # Recupera password reali se mascherate
            existing = load_sync_config() or {}
            mask = '\u25cf\u25cf\u25cf\u25cf\u25cf\u25cf'

            if metodo == 'github':
                gh = data.get('github', {})
                token = gh.get('token', '')
                if token == mask:
                    token = existing.get('github', {}).get('token', '')
                owner = gh.get('owner', '').strip()
                repo = gh.get('repo', '').strip()

                if not token or not owner or not repo:
                    self.send_error_json(400, "Token, owner e repository sono obbligatori")
                    return

                # Test: GET repo info
                api_url = f'https://api.github.com/repos/{owner}/{repo}'
                headers = {
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json',
                    'User-Agent': 'IISS-SitoAdmin/1.0'
                }
                try:
                    req = urllib.request.Request(api_url, headers=headers, method='GET')
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        repo_data = json.loads(resp.read().decode('utf-8'))
                        repo_name = repo_data.get('full_name', f'{owner}/{repo}')
                        self.send_json({"ok": True, "messaggio": f"Connessione riuscita a {repo_name}"})
                        print(f"[OK] Test GitHub riuscito: {repo_name}")
                except urllib.error.HTTPError as e:
                    if e.code == 401:
                        self.send_error_json(400, "Token non valido o scaduto")
                    elif e.code == 404:
                        self.send_error_json(400, f"Repository {owner}/{repo} non trovato")
                    else:
                        self.send_error_json(400, f"Errore GitHub: {e.code} {e.reason}")
                except Exception as e:
                    self.send_error_json(400, f"Errore connessione: {e}")

            elif metodo == 'ftp':
                ftp_data = data.get('ftp', {})
                host = ftp_data.get('host', '').strip()
                porta = int(ftp_data.get('porta', 21))
                username = ftp_data.get('username', '').strip()
                password = ftp_data.get('password', '')
                if password == mask:
                    password = existing.get('ftp', {}).get('password', '')
                percorso = ftp_data.get('percorso_remoto', '/public_html').strip()
                use_tls = bool(ftp_data.get('tls', True))

                if not host or not username:
                    self.send_error_json(400, "Host e username sono obbligatori")
                    return

                ftp = None
                try:
                    if use_tls:
                        ftp = ftplib.FTP_TLS(timeout=15)
                    else:
                        ftp = ftplib.FTP(timeout=15)

                    ftp.connect(host, porta)
                    ftp.login(username, password)
                    if use_tls:
                        ftp.prot_p()
                    if percorso:
                        ftp.cwd(percorso)
                    ftp.quit()
                    self.send_json({"ok": True, "messaggio": f"Connessione FTP riuscita a {host}{percorso}"})
                    print(f"[OK] Test FTP riuscito: {host}")
                except ftplib.error_perm as e:
                    self.send_error_json(400, f"Errore FTP: {e}")
                except Exception as e:
                    self.send_error_json(400, f"Errore connessione FTP: {e}")
                finally:
                    if ftp:
                        try:
                            ftp.close()
                        except Exception:
                            pass
            else:
                self.send_json({"ok": True, "messaggio": "Nessun metodo selezionato"})

        except json.JSONDecodeError:
            self.send_error_json(400, "JSON non valido")
        except Exception as e:
            self.send_error_json(500, f"Errore test connessione: {e}")

    # --- Utility ---
    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def send_error_json(self, code, messaggio):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        resp = {"ok": False, "errore": messaggio}
        self.wfile.write(json.dumps(resp).encode("utf-8"))
        print(f"[ERRORE] {messaggio}")

    def log_message(self, format, *args):
        msg = format % args
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"  [{timestamp}] {msg}")


def main():
    created = init_users()
    with socketserver.ThreadingTCPServer(("", PORT), SitoHandler) as httpd:
        url = f"http://localhost:{PORT}"
        print("=" * 50)
        print("  IISS Giudici Saetta e Livatino")
        print("  Server locale avviato")
        print(f"  Sito:    {url}")
        print(f"  Admin:   {url}/admin.html")
        print("=" * 50)
        if created:
            print("  ** Account admin creato con password predefinita **")
            print("  ** Username: admin / Password: admin1           **")
            print("  ** Cambiare la password al primo accesso!       **")
            print("=" * 50)
        print("  Premi Ctrl+C per chiudere il server")
        print()

        webbrowser.open(f"{url}/admin.html")

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer chiuso.")


if __name__ == "__main__":
    main()
