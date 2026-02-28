"""
Server locale per il sito IISS Giudici Saetta e Livatino.
Serve i file statici e gestisce il salvataggio delle notizie e pagine.
Avviare con: python server.py
"""

import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import webbrowser
import socketserver
import urllib.parse
from datetime import datetime, timedelta
from glob import glob
from http.cookies import SimpleCookie

PORT = 3000
SITE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else os.getcwd()
NOTIZIE_PATH = os.path.join(SITE_DIR, "data", "notizie.json")
PAGINE_DIR = os.path.join(SITE_DIR, "pagine")
USERS_PATH = os.path.join(SITE_DIR, "data", "users.json")

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

            self.send_json({
                "ok": True,
                "messaggio": f"Pagina '{titolo}' salvata con successo",
                "backup": backup_name
            })
            print(f"[OK] Pagina salvata: {filename} (backup: {backup_name})")

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

            # URL relativo a pagine/ (per snippet nell'editor pagine)
            url_pagine = f"../docs/pdf/{cartella}/{final_name}"
            # URL relativo a root (per notizie e link generici)
            url_root = f"docs/pdf/{cartella}/{final_name}"

            self.send_json({
                "ok": True,
                "filename": final_name,
                "url": url_pagine,
                "url_root": url_root,
                "size": len(file_bytes)
            })
            print(f"[OK] File caricato: {filepath} ({len(file_bytes)} bytes)")

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

            self.send_json({"ok": True, "messaggio": f"Salvate {len(notizie)} notizie"})
            print(f"[OK] Salvate {len(notizie)} notizie in {NOTIZIE_PATH}")

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
    with socketserver.TCPServer(("", PORT), SitoHandler) as httpd:
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
