# Changelog

Všechny důležité změny v projektu jsou zdokumentovány zde.

Formát vychází z [Keep a Changelog](https://keepachangelog.com/cs/1.0.0/).

---

## [1.0.0] — 2025-03

### Přidáno
- Interaktivní mapa s geocódovanými partnerskými servisy
- Vyhledávání podle názvu firmy nebo adresy
- Detail firmy s odkazem na web a Mapy.cz
- Admin panel pro nahrání a validaci nového CSV
- Dvoukrokový proces aktualizace dat (validate → commit)
- Cache geocódovaných adres — šetří API volání
- Filtrování neaktivních firem podle sloupce `Aktivní/Neaktivní`
- Uložení pending CSV na disk (místo session) — podpora velkých souborů
- Dynamický session key odvozený z `ADMIN_USERNAME`
- Normalizace konce řádků (`\r\r\n`) z Excel exportů
