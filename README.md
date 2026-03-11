# Weilovka — Mapa smluvních servisů

Interaktivní webová mapa smluvních autoservisů školy. Zobrazuje geocódované partnery načtené z CSV souboru na mapě s možností vyhledávání. Administrátoři mohou aktualizovat data přes zabezpečený admin panel.

---

## Funkce

- Interaktivní mapa (Leaflet + OpenStreetMap) se všemi aktivními partnery
- Vyhledávání podle názvu firmy nebo adresy
- Detail firmy s odkazem na web a Mapy.cz
- Admin panel pro nahrání nového CSV
- Geocódování adres přes [Mapy.com API](https://api.mapy.com)
- Cache geocódovaných adres (JSON) — opakované nahrání stejného CSV nevolá API zbytečně
- Filtrování neaktivních firem (`Aktivní/Neaktivní = TRUE` se přeskočí)

---

## Technologie

| Vrstva    | Technologie                            |
|-----------|----------------------------------------|
| Frontend  | React 18, Vite, Leaflet, React-Leaflet |
| Backend   | Python 3.11+, Flask, Flask-CORS        |
| Geocoding | Mapy.com API v1                        |
| Styling   | CSS (vlastní, bez frameworku)          |

---

## Struktura projektu

```
weilovka/
├── backend/
│   ├── app.py                  # Flask API server
│   ├── .env                    # Secrets (není v gitu!)
│   ├── .env.example            # Šablona pro .env
│   ├── requirements.txt
│   └── data/
│       ├── data_source.csv     # Aktuální CSV (není v gitu!)
│       └── geocode_cache.json  # Cache souřadnic (není v gitu!)
└── frontend/
    ├── src/
    │   ├── App.jsx
    │   ├── main.jsx
    │   ├── styles.css
    │   └── components/
    │       ├── Main.jsx
    │       └── Main.css
    ├── index.html
    ├── vite.config.js
    └── package.json
```

---

## Instalace a spuštění

### Požadavky

- Python 3.11+
- Node.js 18+
- API klíč pro [Mapy.com API](https://developer.mapy.cz)

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

pip install -r requirements.txt
```

Vytvoř soubor `.env` podle šablony `.env.example`:

```env
SECRET_KEY=nahodne-dlouhe-heslo
MAPYCZ_API_KEY=tvuj-mapy-api-klic
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=sha256-hash-hesla
```

Hash hesla vygeneruješ takto:
```bash
python -c "import hashlib; print(hashlib.sha256('tvoje_heslo'.encode()).hexdigest())"
```

Spuštění:
```bash
python app.py
```

Server běží na `http://localhost:5000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend běží na `http://localhost:5173`.

Pro produkční build:
```bash
npm run build
```

---

## Formát CSV

CSV musí mít jako první řádek header s polem `Firma`. Podporované sloupce:

| Sloupec | Index | Popis |
|---------|-------|-------|
| Firma | 0 | Název firmy |
| Ulice | 1 | Ulice a číslo popisné |
| Město | 2 | Město |
| Web | 3 | Webová adresa (bez https://) |
| Aktivní/Neaktivní | 4 | `TRUE` = neaktivní (přeskočí se), `FALSE` = aktivní |

Oddělovač: `;` (středník)  
Kódování: UTF-8 nebo UTF-8 BOM

Příklad:
```
Firma;Ulice;Město;Web;Aktivní/Neaktivní
HAVEX auto s.r.o.;Jateční 317/41;Praha 7;www.havex.cz;FALSE
Neaktivní servis s.r.o.;Příkladná 1;Praha 1;www.priklad.cz;TRUE
```

---

## API endpointy

### Veřejné

| Metoda | Endpoint | Popis |
|--------|----------|-------|
| GET | `/api/map-data` | Vrátí všechny geocódované aktivní firmy |
| GET | `/api/status` | Statistiky geocódování (total/geocoded/missing) |

### Admin (vyžaduje přihlášení)

| Metoda | Endpoint | Popis |
|--------|----------|-------|
| POST | `/api/admin/login` | Přihlášení `{username, password}` |
| POST | `/api/admin/logout` | Odhlášení |
| GET | `/api/admin/me` | Stav přihlášení |
| POST | `/api/admin/validate` | Nahrání a validace CSV (multipart/form-data, pole `file`) |
| POST | `/api/admin/commit` | Potvrzení a uložení validovaného CSV |

---

## Nasazení (produkce)

1. Nastav `debug=False` v `app.py` (již nastaveno)
2. Použij produkční WSGI server (např. Gunicorn):
   ```bash
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:5000 app:app
   ```
3. Nastav reverse proxy (nginx/Apache) před Flask
4. Frontend build (`npm run build`) nasaď na statický hosting nebo přes nginx

---

## Licence

Tento projekt je licencován pod licencí **Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International (CC BY-NC-ND 4.0)**.

- ✅ Projekt lze volně sdílet a prohlížet
- ✅ Při sdílení musí být uvedeno autorství školy
- ❌ Komerční využití není povoleno
- ❌ Šíření upravených verzí bez souhlasu autora není povoleno
- ✅ Data firem jsou majetkem školy a jsou chráněna samostatně

Viz [LICENSE](LICENSE) pro plné znění.
