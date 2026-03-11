from flask import Flask, jsonify, request, session, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import csv, os, json, urllib.request, urllib.parse, hashlib, io, logging

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, supports_credentials=True)

app.secret_key = os.getenv('SECRET_KEY')
if not app.secret_key:
    raise RuntimeError("SECRET_KEY chybí v .env")

BASE_DIR            = os.path.dirname(os.path.abspath(__file__))
CSV_FILE_PATH       = os.path.join(BASE_DIR, 'data', 'data_source.csv')
CACHE_FILE_PATH     = os.path.join(BASE_DIR, 'data', 'geocode_cache.json')
PENDING_CSV_PATH    = os.path.join(BASE_DIR, 'data', 'pending.csv')
MAPYCZ_API_KEY      = os.getenv('MAPYCZ_API_KEY')
ADMIN_USERNAME      = os.getenv('ADMIN_USERNAME')
ADMIN_PASSWORD_HASH = os.getenv('ADMIN_PASSWORD_HASH')

for key in ('MAPYCZ_API_KEY', 'ADMIN_USERNAME', 'ADMIN_PASSWORD_HASH'):
    if not os.getenv(key):
        raise RuntimeError(f"{key} chybí v .env")

SESSION_KEY = hashlib.sha256(ADMIN_USERNAME.encode()).hexdigest()[:16]

# ── Helpers ───────────────────────────────────────────────────────────────────

def is_logged_in():
    return session.get(SESSION_KEY) is True

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
    Parse CSV into list of active businesses.
    Columns: Firma(0), Ulice(1), Město(2), Web(3), Aktivní/Neaktivní(4)
    Skips rows where column 4 is 'TRUE' (= neaktivní).
    Only counts truly empty/malformed rows toward the stop condition.
    """
    content = content.replace('\r\r\n', '\n').replace('\r\n', '\n').replace('\r', '\n')
    businesses, started, empty = [], False, 0
    for row in csv.reader(io.StringIO(content), delimiter=';'):
        if not started:
            if row and 'Firma' in row[0]:
                started = True
            continue
        if len(row) >= 4:
            name, street, city, web = (c.strip() for c in row[:4])
            inactive = len(row) >= 5 and row[4].strip().upper() == 'TRUE'
            if name and street and city and name.lower() not in ('firma', 'celkem'):
                empty = 0  # reset empty counter for any valid row, active or not
                if not inactive:
                    businesses.append({'name': name, 'address': f'{street}, {city}', 'web': web})
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

    if username == ADMIN_USERNAME and pw_hash == ADMIN_PASSWORD_HASH:
        session[SESSION_KEY] = True
        log.info("Admin login: %s", username)
        return jsonify({'ok': True})

    log.warning("Failed login: %s", username)
    return jsonify({'ok': False, 'error': 'Nesprávné jméno nebo heslo'}), 401

@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    session.clear()
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
        return jsonify({'error': "CSV musí obsahovat řádek s 'Firma'"}), 400

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

    os.makedirs(os.path.dirname(PENDING_CSV_PATH), exist_ok=True)
    with open(PENDING_CSV_PATH, 'w', encoding='utf-8-sig') as f:
        f.write(content)
    session['pending'] = True

    return jsonify({'total': len(results), 'ok': len(results) - failed, 'failed': failed, 'results': results})

@app.route('/api/admin/commit', methods=['POST'])
def admin_commit():
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401
    if not session.get('pending') or not os.path.exists(PENDING_CSV_PATH):
        return jsonify({'error': 'Nejdřív spusť /validate'}), 400

    with open(PENDING_CSV_PATH, encoding='utf-8-sig') as f:
        pending = f.read()

    businesses = parse_csv(pending)
    cache      = geocode_all(businesses)

    os.makedirs(os.path.dirname(CSV_FILE_PATH), exist_ok=True)
    with open(CSV_FILE_PATH, 'w', encoding='utf-8-sig') as f:
        f.write(pending)

    session.pop('pending', None)
    os.remove(PENDING_CSV_PATH)

    geocoded = sum(1 for b in businesses if cache.get(b['address'], {}).get('lat'))
    log.info("Commit: %d/%d geokódováno", geocoded, len(businesses))
    return jsonify({'ok': True, 'total': len(businesses), 'geocoded': geocoded,
                    'message': f'CSV uložen. {geocoded}/{len(businesses)} adres geokódováno.'})

# ── Static ────────────────────────────────────────────────────────────────────

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/admin')
def admin_panel():
    return send_from_directory(BASE_DIR, 'admin.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)