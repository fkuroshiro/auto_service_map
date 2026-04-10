"""
Weilovka Mapa – Flask backend
Production-ready version
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import logging
import os
import secrets
import time
import urllib.parse
import urllib.request
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

_REQUIRED_ENV = ("SECRET_KEY", "MAPYCZ_API_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD_HASH")

def _require_env(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        raise RuntimeError(f"Chybí povinná proměnná prostředí: {key}")
    return value


@dataclass(frozen=True)
class Config:
    secret_key: str
    mapycz_api_key: str
    admin_username: str
    admin_password_hash: str
    allowed_origins: list[str]
    base_dir: Path
    csv_path: Path
    cache_path: Path
    pending_path: Path
    token_ttl: int = 3600          # sekund — 1 hodina
    max_tokens: int = 50
    rate_limit_attempts: int = 5
    rate_limit_window: int = 900   # sekund — 15 minut
    max_upload_bytes: int = 2 * 1024 * 1024  # 2 MB

    @classmethod
    def from_env(cls) -> "Config":
        for key in _REQUIRED_ENV:
            _require_env(key)  # selže rychle pokud něco chybí

        base = Path(__file__).parent.resolve()
        data = base / "data"

        origins_raw = os.getenv("ALLOWED_ORIGINS", "")
        origins = [o.strip() for o in origins_raw.split(",") if o.strip()]

        return cls(
            secret_key=_require_env("SECRET_KEY"),
            mapycz_api_key=_require_env("MAPYCZ_API_KEY"),
            admin_username=_require_env("ADMIN_USERNAME"),
            admin_password_hash=_require_env("ADMIN_PASSWORD_HASH"),
            allowed_origins=origins,
            base_dir=base,
            csv_path=data / "data_source.csv",
            cache_path=data / "geocode_cache.json",
            pending_path=data / "pending.csv",
        )


cfg = Config.from_env()

# ── Flask app ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = cfg.secret_key
app.config["MAX_CONTENT_LENGTH"] = cfg.max_upload_bytes

CORS(
    app,
    origins=cfg.allowed_origins or "*",  # "*" pokud ALLOWED_ORIGINS není nastaveno
    supports_credentials=True,
)

# ── Token store ───────────────────────────────────────────────────────────────

@dataclass
class _TokenEntry:
    data: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class TokenStore:
    """Thread-safe in-memory token store s automatickým expiry."""

    def __init__(self, ttl: int, max_tokens: int) -> None:
        self._store: dict[str, _TokenEntry] = {}
        self._lock = Lock()
        self._ttl = ttl
        self._max = max_tokens

    # -- internal --

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [t for t, e in self._store.items() if now - e.created_at > self._ttl]
        for t in expired:
            del self._store[t]

    # -- public --

    def create(self) -> str:
        with self._lock:
            self._purge_expired()
            if len(self._store) >= self._max:
                log.warning("Token store plný (%d tokenů); nejstarší je odstraněn", self._max)
                oldest = min(self._store, key=lambda t: self._store[t].created_at)
                del self._store[oldest]
            token = secrets.token_hex(32)
            self._store[token] = _TokenEntry()
            return token

    def valid(self, token: str | None) -> bool:
        if not token:
            return False
        with self._lock:
            entry = self._store.get(token)
            if entry is None:
                return False
            if time.time() - entry.created_at > self._ttl:
                del self._store[token]
                return False
            return True

    def get(self, token: str | None, key: str, default: Any = None) -> Any:
        if not token:
            return default
        with self._lock:
            entry = self._store.get(token)
            return entry.data.get(key, default) if entry else default

    def set(self, token: str | None, key: str, value: Any) -> None:
        if not token:
            return
        with self._lock:
            entry = self._store.get(token)
            if entry:
                entry.data[key] = value

    def remove(self, token: str | None) -> None:
        if token:
            with self._lock:
                self._store.pop(token, None)


_tokens = TokenStore(ttl=cfg.token_ttl, max_tokens=cfg.max_tokens)

# ── Rate limiter ──────────────────────────────────────────────────────────────

class RateLimiter:
    """Sliding-window rate limiter per IP."""

    def __init__(self, max_attempts: int, window: int) -> None:
        self._attempts: dict[str, list[float]] = {}
        self._lock = Lock()
        self._max = max_attempts
        self._window = window

    def is_blocked(self, ip: str) -> bool:
        now = time.time()
        with self._lock:
            history = [t for t in self._attempts.get(ip, []) if now - t < self._window]
            self._attempts[ip] = history
            return len(history) >= self._max

    def record(self, ip: str) -> None:
        with self._lock:
            self._attempts.setdefault(ip, []).append(time.time())


_login_limiter = RateLimiter(cfg.rate_limit_attempts, cfg.rate_limit_window)

# ── Request helpers ───────────────────────────────────────────────────────────

def _get_token() -> str | None:
    return request.headers.get("X-Admin-Token") or None


def _is_logged_in() -> bool:
    return _tokens.valid(_get_token())


def _client_ip() -> str:
    return request.headers.get("CF-Connecting-IP") or request.remote_addr or "unknown"

# ── CSV helpers ───────────────────────────────────────────────────────────────

_COL_NAME, _COL_STREET, _COL_CITY, _COL_PSC, _COL_WEB, _COL_ACTIVE = range(6)


def parse_csv(content: str) -> list[dict]:
    """
    Parsuje CSV se středníkem jako oddělovačem.
    Sloupce: name | street | city | psc | web | isActive
    Vrací jen řádky s isActive == '1'.
    """
    content = content.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    businesses: list[dict] = []
    started = False
    consecutive_empty = 0

    for row in csv.reader(io.StringIO(content), delimiter=";"):
        if not started:
            if (
                len(row) > _COL_ACTIVE
                and row[_COL_NAME].strip() == "name"
                and row[_COL_ACTIVE].strip() == "isActive"
            ):
                started = True
            continue

        if len(row) > _COL_ACTIVE:
            name = row[_COL_NAME].strip()
            street = row[_COL_STREET].strip()
            city = row[_COL_CITY].strip()
            web = row[_COL_WEB].strip() if len(row) > _COL_WEB else ""
            is_active = row[_COL_ACTIVE].strip()

            if name and street and city:
                consecutive_empty = 0
                if is_active == "1":
                    businesses.append(
                        {"name": name, "address": f"{street}, {city}", "web": web}
                    )
                continue

        consecutive_empty += 1
        if consecutive_empty >= 4:
            break

    return businesses


def _read_csv() -> list[dict]:
    if not cfg.csv_path.exists():
        return []
    with cfg.csv_path.open(encoding="utf-8-sig") as f:
        return parse_csv(f.read())


def _decode_upload(raw: bytes) -> str:
    """Zkusí dekódovat bytes postupně přes běžná kódování."""
    for enc in ("utf-8-sig", "utf-8", "cp1250", "latin1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("Nepodařilo se dekódovat soubor (zkuste UTF-8 nebo Windows-1250)")


def _atomic_write(path: Path, content: str, encoding: str = "utf-8-sig") -> None:
    """Zapíše soubor atomicky přes dočasný soubor (zabraňuje partial writes)."""
    tmp = path.with_suffix(".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(content, encoding=encoding)
    tmp.replace(path)

# ── Geocoding ─────────────────────────────────────────────────────────────────

def _load_cache() -> dict:
    try:
        with cfg.cache_path.open(encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict) -> None:
    cfg.cache_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(cache, ensure_ascii=False, indent=2)
    _atomic_write(cfg.cache_path, content, encoding="utf-8")


def _geocode(address: str) -> dict:
    params = urllib.parse.urlencode(
        {
            "query": f"{address}, Česká republika",
            "lang": "cs",
            "limit": 1,
            "type": "regional.address",
            "apikey": cfg.mapycz_api_key,
        }
    )
    try:
        req = urllib.request.Request(
            f"https://api.mapy.com/v1/geocode?{params}",
            headers={"User-Agent": "skola-autoobory-map/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        pos = (data.get("items") or [{}])[0].get("position", {})
        lat, lng = pos.get("lat"), pos.get("lon")
        if lat and lng:
            return {"lat": round(float(lat), 6), "lng": round(float(lng), 6)}
        return {"lat": None, "lng": None, "error": "Adresa nenalezena"}
    except urllib.error.URLError as e:
        log.warning("Geocoding URLError pro '%s': %s", address, e)
        return {"lat": None, "lng": None, "error": str(e)}
    except Exception as e:
        log.error("Geocoding neočekávaná chyba pro '%s': %s", address, e)
        return {"lat": None, "lng": None, "error": str(e)}


def _diff_and_update_cache(
    old_businesses: list[dict], new_businesses: list[dict]
) -> dict:
    old_addrs = {b["address"] for b in old_businesses}
    new_addrs = {b["address"] for b in new_businesses}
    added = new_addrs - old_addrs
    removed = old_addrs - new_addrs
    kept = old_addrs & new_addrs

    log.info("Diff: %d zachováno, %d přidáno, %d odstraněno", len(kept), len(added), len(removed))

    cache = _load_cache()

    for addr in removed:
        cache.pop(addr, None)
        log.info("Cache: odstraněno '%s'", addr)

    for addr in added:
        result = _geocode(addr)
        cache[addr] = result
        if result.get("lat"):
            log.info("Cache: geokódováno '%s'", addr)
        else:
            log.warning("Cache: geokódování selhalo '%s' – %s", addr, result.get("error"))

    _save_cache(cache)
    return cache

# ── Public endpoints ──────────────────────────────────────────────────────────

@app.get("/api/map-data")
def map_data():
    businesses = _read_csv()
    cache = _load_cache()
    return jsonify(
        [
            {
                "name": b["name"],
                "address": b["address"],
                "lat": cache[b["address"]]["lat"],
                "lng": cache[b["address"]]["lng"],
                "web": b["web"],
            }
            for b in businesses
            if cache.get(b["address"], {}).get("lat")
        ]
    )


@app.get("/api/status")
def status():
    businesses = _read_csv()
    cache = _load_cache()
    geocoded = sum(1 for b in businesses if cache.get(b["address"], {}).get("lat"))
    return jsonify(
        {
            "total": len(businesses),
            "geocoded": geocoded,
            "missing": len(businesses) - geocoded,
        }
    )

# ── Admin auth ────────────────────────────────────────────────────────────────

@app.post("/api/admin/login")
def admin_login():
    ip = _client_ip()

    if _login_limiter.is_blocked(ip):
        log.warning("Login rate-limit hit: %s", ip)
        return jsonify({"ok": False, "error": "Příliš mnoho pokusů. Zkuste to za chvíli."}), 429

    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    pw_hash = hashlib.sha256(password.encode()).hexdigest()

    if username == cfg.admin_username and hmac.compare_digest(pw_hash, cfg.admin_password_hash):
        token = _tokens.create()
        log.info("Admin login: %s z %s", username, ip)
        return jsonify({"ok": True, "token": token})

    _login_limiter.record(ip)
    log.warning("Neúspěšný login pro '%s' z %s", username, ip)
    return jsonify({"ok": False, "error": "Nesprávné jméno nebo heslo"}), 401


@app.post("/api/admin/logout")
def admin_logout():
    _tokens.remove(_get_token())
    return jsonify({"ok": True})


@app.get("/api/admin/me")
def admin_me():
    return jsonify({"logged_in": _is_logged_in()})

# ── Admin CSV ─────────────────────────────────────────────────────────────────

@app.post("/api/admin/validate")
def admin_validate():
    if not _is_logged_in():
        return jsonify({"error": "Unauthorized"}), 401

    if "file" not in request.files:
        return jsonify({"error": 'V požadavku chybí soubor (klíč "file")'}), 400

    file = request.files["file"]
    filename = file.filename or ""

    if not filename:
        return jsonify({"error": "Nebyl vybrán žádný soubor"}), 400
    if not filename.lower().endswith(".csv"):
        return jsonify({"error": f'Soubor "{filename}" není CSV'}), 400

    try:
        raw_data = file.read()
        content = _decode_upload(raw_data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    businesses = parse_csv(content)
    if not businesses:
        return jsonify(
            {
                "error": (
                    "V souboru nebyla nalezena žádná data. "
                    "Zkontrolujte, zda používáte středník (;) jako oddělovač."
                )
            }
        ), 400

    cache = _load_cache()
    results: list[dict] = []
    failed = 0

    for b in businesses:
        addr = b["address"]
        cached = cache.get(addr, {})
        if cached.get("lat"):
            results.append({**b, "status": "ok", "lat": cached["lat"], "lng": cached["lng"], "cached": True, "error": None})
        else:
            geo = _geocode(addr)
            if geo.get("lat"):
                results.append({**b, "status": "ok", "lat": geo["lat"], "lng": geo["lng"], "cached": False, "error": None})
                cache[addr] = {"lat": geo["lat"], "lng": geo["lng"]}
            else:
                failed += 1
                results.append({**b, "status": "failed", "lat": None, "lng": None, "cached": False, "error": geo.get("error")})

    _save_cache(cache)
    _atomic_write(cfg.pending_path, content)
    _tokens.set(_get_token(), "pending", True)

    return jsonify({"total": len(results), "ok": len(results) - failed, "failed": failed, "results": results})


@app.post("/api/admin/commit")
def admin_commit():
    if not _is_logged_in():
        return jsonify({"error": "Unauthorized"}), 401

    token = _get_token()
    if not _tokens.get(token, "pending") or not cfg.pending_path.exists():
        return jsonify({"error": "Nejdřív spusť /validate"}), 400

    pending_content = cfg.pending_path.read_text(encoding="utf-8-sig")
    new_businesses = parse_csv(pending_content)
    old_businesses = _read_csv()

    cache = _diff_and_update_cache(old_businesses, new_businesses)

    _atomic_write(cfg.csv_path, pending_content)
    _tokens.set(token, "pending", False)
    cfg.pending_path.unlink(missing_ok=True)

    old_addrs = {b["address"] for b in old_businesses}
    new_addrs = {b["address"] for b in new_businesses}
    added = len(new_addrs - old_addrs)
    removed = len(old_addrs - new_addrs)
    geocoded = sum(1 for b in new_businesses if cache.get(b["address"], {}).get("lat"))

    log.info(
        "Commit: %d/%d geokódováno, +%d přidáno, -%d odstraněno",
        geocoded, len(new_businesses), added, removed,
    )

    return jsonify(
        {
            "ok": True,
            "total": len(new_businesses),
            "geocoded": geocoded,
            "added": added,
            "removed": removed,
            "message": (
                f"CSV uložen. {geocoded}/{len(new_businesses)} adres geokódováno. "
                f"+{added} nových, -{removed} odstraněných provozoven."
            ),
        }
    )

# ── Static ────────────────────────────────────────────────────────────────────

@app.get("/favicon.ico")
def favicon():
    return send_from_directory(str(cfg.base_dir), "skolahostivar.ico")


@app.get("/admin")
def admin_panel():
    return send_from_directory(str(cfg.base_dir), "admin.html")


# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(413)
def too_large(_e):
    return jsonify({"error": f"Soubor je příliš velký (max {cfg.max_upload_bytes // 1024 // 1024} MB)"}), 413


@app.errorhandler(405)
def method_not_allowed(_e):
    return jsonify({"error": "Metoda není povolena"}), 405


@app.errorhandler(404)
def not_found(_e):
    return jsonify({"error": "Endpoint nenalezen"}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)