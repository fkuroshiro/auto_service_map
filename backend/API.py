from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import csv, os, json, urllib.request, urllib.parse, hashlib, hmac, secrets, io, logging

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, supports_credentials=True)

app.secret_key = os.getenv('SECRET_KEY')  # kept for any future use

BASE_DIR            = os.path.dirname(os.path.abspath(__file__))
CSV_FILE_PATH       = os.path.join(BASE_DIR, 'data', 'data_source.csv')
CACHE_FILE_PATH     = os.path.join(BASE_DIR, 'data', 'geocode_cache.json')
PENDING_CSV_PATH    = os.path.join(BASE_DIR, 'data', 'pending.csv')
MAPYCZ_API_KEY      = os.getenv('MAPYCZ_API_KEY')
ADMIN_USERNAME      = os.getenv('ADMIN_USERNAME')
ADMIN_PASSWORD_HASH = os.getenv('ADMIN_PASSWORD_HASH')

for key in ('SECRET_KEY', 'MAPYCZ_API_KEY', 'ADMIN_USERNAME', 'ADMIN_PASSWORD_HASH'):
    if not os.getenv(key):
        raise RuntimeError(f"{key} chybí v .env")

# ── In-memory token store ─────────────────────────────────────────────────────
# Maps token → {'pending': bool}
# Resets on server restart — intentional, forces re-login after deploy.
_tokens: dict = {}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_token() -> str | None:
    """Extract token from custom header (Cloudflare strips Authorization)."""
    return request.headers.get('X-Admin-Token') or None

def is_logged_in() -> bool:
    token = _get_token()
    return token is not None and token in _tokens

def get_token_data() -> dict:
    token = _get_token()
    return _tokens.get(token, {}) if token else {}

def set_token_data(key: str, value) -> None:
    token = _get_token()
    if token and token in _tokens:
        _tokens[token][key] = value

def load_cache():
    try:
        with open(CACHE_FILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_FILE_PATH), exist_ok=True)
    with open(CACHE_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def parse_csv(content):
    """
    Parse the new Excel-exported CSV format into a list of active businesses.

    The file has a variable-length header block followed by a marker row
    containing the column aliases used as a schema map:
        name | street | city | psc | web | isActive  (columns 0-5)

    Data rows start immediately after that marker row.
    Only rows where isActive == '1' are included.
    Parsing stops after 4 consecutive empty/malformed rows.
    """
    content = content.replace('\r\r\n', '\n').replace('\r\n', '\n').replace('\r', '\n')

    businesses = []
    started    = False
    empty      = 0

    COL_NAME   = 0
    COL_STREET = 1
    COL_CITY   = 2
    COL_PSC    = 3
    COL_WEB    = 4
    COL_ACTIVE = 5

    for row in csv.reader(io.StringIO(content), delimiter=','):
        if not started:
            if len(row) > COL_ACTIVE and row[COL_NAME].strip() == 'name' and row[COL_ACTIVE].strip() == 'isActive':
                started = True
            continue

        if len(row) > COL_ACTIVE:
            name      = row[COL_NAME].strip()
            street    = row[COL_STREET].strip()
            city      = row[COL_CITY].strip()
            web       = row[COL_WEB].strip() if len(row) > COL_WEB else ''
            is_active = row[COL_ACTIVE].strip()

            if name and street and city:
                empty = 0
                if is_active == '1':
                    businesses.append({
                        'name':    name,
                        'address': f'{street}, {city}',
                        'web':     web,
                    })
                continue

        empty += 1
        if empty >= 4:
            break

    return businesses

def read_csv():
    if not os.path.exists(CSV_FILE_PATH):
        return []
    with open(CSV_FILE_PATH, encoding='utf-8-sig') as f:
        return parse_csv(f.read())

def geocode(address):
    params = urllib.parse.urlencode({
        'query': f'{address}, Česká republika',
        'lang': 'cs', 'limit': 1,
        'type': 'regional.address',
        'apikey': MAPYCZ_API_KEY,
    })
    try:
        req = urllib.request.Request(
            f'https://api.mapy.com/v1/geocode?{params}',
            headers={'User-Agent': 'skola-autoobory-map/1.0'}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        pos = (data.get('items') or [{}])[0].get('position', {})
        lat, lng = pos.get('lat'), pos.get('lon')
        if lat and lng:
            return {'lat': round(float(lat), 6), 'lng': round(float(lng), 6)}
        return {'lat': None, 'lng': None, 'error': 'Adresa nenalezena'}
    except Exception as e:
        return {'lat': None, 'lng': None, 'error': str(e)}

def geocode_all(businesses):
    cache = load_cache()
    for b in businesses:
        if not cache.get(b['address'], {}).get('lat'):
            cache[b['address']] = geocode(b['address'])
    save_cache(cache)
    return cache

def diff_and_update_cache(old_businesses, new_businesses):
    """
    Compare old vs new business lists and return a pruned, updated cache.

    - Addresses present in new but missing from cache  → geocoded (new entries)
    - Addresses present in old but absent from new     → removed from cache
    - Addresses present in both                        → cache entry kept as-is
    """
    old_addresses = {b['address'] for b in old_businesses}
    new_addresses = {b['address'] for b in new_businesses}

    added   = new_addresses - old_addresses
    removed = old_addresses - new_addresses
    kept    = old_addresses & new_addresses

    log.info("Diff: %d zachováno, %d přidáno, %d odstraněno", len(kept), len(added), len(removed))

    cache = load_cache()

    for addr in removed:
        cache.pop(addr, None)
        log.info("Cache: odstraněno '%s'", addr)

    for addr in added:
        result = geocode(addr)
        cache[addr] = result
        if result.get('lat'):
            log.info("Cache: geokódováno '%s'", addr)
        else:
            log.warning("Cache: geokódování selhalo '%s' – %s", addr, result.get('error'))

    save_cache(cache)
    return cache

# ── Public API ────────────────────────────────────────────────────────────────

@app.route('/api/map-data')
def map_data():
    businesses, cache = read_csv(), load_cache()
    return jsonify([
        {'name': b['name'], 'address': b['address'],
         'lat': cache[b['address']]['lat'], 'lng': cache[b['address']]['lng'], 'web': b['web']}
        for b in businesses if cache.get(b['address'], {}).get('lat')
    ])

@app.route('/api/status')
def status():
    businesses, cache = read_csv(), load_cache()
    geocoded = sum(1 for b in businesses if cache.get(b['address'], {}).get('lat'))
    return jsonify({'total': len(businesses), 'geocoded': geocoded, 'missing': len(businesses) - geocoded})

# ── Admin Auth ────────────────────────────────────────────────────────────────

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data     = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    pw_hash  = hashlib.sha256(password.encode()).hexdigest()

    if username == ADMIN_USERNAME and hmac.compare_digest(pw_hash, ADMIN_PASSWORD_HASH):
        token = secrets.token_hex(32)
        _tokens[token] = {'pending': False}
        log.info("Admin login: %s", username)
        return jsonify({'ok': True, 'token': token})

    log.warning("Failed login: %s", username)
    return jsonify({'ok': False, 'error': 'Nesprávné jméno nebo heslo'}), 401

@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    token = _get_token()
    if token:
        _tokens.pop(token, None)
    return jsonify({'ok': True})

@app.route('/api/admin/me')
def admin_me():
    return jsonify({'logged_in': is_logged_in()})

# ── Admin CSV ─────────────────────────────────────────────────────────────────

@app.route('/api/admin/validate', methods=['POST'])
def admin_validate():
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401

    file = request.files.get('file')
    if not file or not file.filename.endswith('.csv'):
        return jsonify({'error': 'Nahraj .csv soubor'}), 400

    content    = file.read().decode('utf-8-sig')
    businesses = parse_csv(content)
    if not businesses:
        return jsonify({'error': "CSV musí obsahovat řádek s 'name' a 'isActive'"}), 400

    cache, results, failed = load_cache(), [], 0
    for b in businesses:
        addr   = b['address']
        cached = cache.get(addr, {})
        if cached.get('lat'):
            results.append({**b, 'status': 'ok', 'lat': cached['lat'], 'lng': cached['lng'], 'cached': True, 'error': None})
        else:
            geo = geocode(addr)
            if geo.get('lat'):
                results.append({**b, 'status': 'ok', 'lat': geo['lat'], 'lng': geo['lng'], 'cached': False, 'error': None})
            else:
                failed += 1
                results.append({**b, 'status': 'failed', 'lat': None, 'lng': None, 'cached': False, 'error': geo.get('error')})

    # Ulož nově geokódované výsledky do cache hned při validate
    for r in results:
        if r['status'] == 'ok' and not r['cached']:
            cache[r['address']] = {'lat': r['lat'], 'lng': r['lng']}
    save_cache(cache)

    os.makedirs(os.path.dirname(PENDING_CSV_PATH), exist_ok=True)
    with open(PENDING_CSV_PATH, 'w', encoding='utf-8-sig') as f:
        f.write(content)
    set_token_data('pending', True)

    return jsonify({'total': len(results), 'ok': len(results) - failed, 'failed': failed, 'results': results})

@app.route('/api/admin/commit', methods=['POST'])
def admin_commit():
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401
    if not get_token_data().get('pending') or not os.path.exists(PENDING_CSV_PATH):
        return jsonify({'error': 'Nejdřív spusť /validate'}), 400

    with open(PENDING_CSV_PATH, encoding='utf-8-sig') as f:
        pending = f.read()

    new_businesses = parse_csv(pending)
    old_businesses = read_csv()

    cache = diff_and_update_cache(old_businesses, new_businesses)

    os.makedirs(os.path.dirname(CSV_FILE_PATH), exist_ok=True)
    with open(CSV_FILE_PATH, 'w', encoding='utf-8-sig') as f:
        f.write(pending)

    set_token_data('pending', False)
    os.remove(PENDING_CSV_PATH)

    old_addresses = {b['address'] for b in old_businesses}
    new_addresses = {b['address'] for b in new_businesses}
    added         = len(new_addresses - old_addresses)
    removed       = len(old_addresses - new_addresses)
    geocoded      = sum(1 for b in new_businesses if cache.get(b['address'], {}).get('lat'))

    log.info("Commit: %d/%d geokódováno, +%d přidáno, -%d odstraněno",
             geocoded, len(new_businesses), added, removed)

    return jsonify({
        'ok':       True,
        'total':    len(new_businesses),
        'geocoded': geocoded,
        'added':    added,
        'removed':  removed,
        'message':  (
            f'CSV uložen. {geocoded}/{len(new_businesses)} adres geokódováno. '
            f'+{added} nových, -{removed} odstraněných provozoven.'
        ),
    })

# ── Static ────────────────────────────────────────────────────────────────────

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/admin')
def admin_panel():
    return send_from_directory(BASE_DIR, 'admin.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
