import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";
import L from "leaflet";
import markerIcon    from "leaflet/dist/images/marker-icon.png";
import markerShadow  from "leaflet/dist/images/marker-shadow.png";
import markerIcon2x  from "leaflet/dist/images/marker-icon-2x.png";
import "./main.css";

// Fix Leaflet default marker icons in Vite
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconUrl:       markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl:     markerShadow,
  iconSize:      [25, 41],
  iconAnchor:    [12, 41],
  popupAnchor:   [1, -34],
  shadowSize:    [41, 41],
});

/** Normalize a bare URL to include https:// */
function toAbsoluteUrl(url) {
  if (!url) return null;
  return url.startsWith("http") ? url : `https://${url}`;
}

/** Full address string from a service object */
function fullAddress(s) {
  return s.city ? `${s.address}, ${s.city}` : s.address;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function MapView({ services, onSelect }) {
  return (
    <MapContainer
      center={[50.0755, 14.4378]}
      zoom={10}
      className="map-container"
      scrollWheelZoom
    >
      <TileLayer
        attribution="&copy; OpenStreetMap"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {services
        .filter(s => s.lat && s.lng)
        .map(s => (
          <Marker
            key={s.id}
            position={[s.lat, s.lng]}
            eventHandlers={{ click: () => onSelect(s) }}
          >
            <Popup>
              <strong>{s.name}</strong><br />
              {fullAddress(s)}
            </Popup>
          </Marker>
        ))}
    </MapContainer>
  );
}

function ServiceDetail({ service }) {
  if (!service) return null;

  const webUrl = toAbsoluteUrl(service.web);
  const mapUrl = `https://mapy.cz/zakladni?q=${encodeURIComponent(fullAddress(service))}`;

  return (
    <div className="service-detail">
      <h3>{service.name}</h3>
      <p className="service-detail__address">{fullAddress(service)}</p>
      <div className="service-detail__links">
        {webUrl && (
          <a href={webUrl} target="_blank" rel="noreferrer" className="btn-link">
            Web servisu
          </a>
        )}
        <a href={mapUrl} target="_blank" rel="noreferrer" className="btn-link">
          Otevřít v mapě
        </a>
      </div>
    </div>
  );
}

// ── Main export ───────────────────────────────────────────────────────────────

export default function Main({
  services, selectedService, onSelect,
  searchQuery, onSearchChange,
  loading, error,
}) {
  return (
    <main className="main-content">
      <div className="content-wrapper">
        <h2 className="section-title">Seznam firem pro praxi žáků autooborů</h2>

        {loading && <div className="state-box">Načítám data…</div>}
        {error   && <div className="state-box state-box--error">{error}</div>}

        {!loading && !error && (
          <div className="layout">

            {/* LEFT — search + table + detail */}
            <div className="layout__left">
              <div className="filters">
                <input
                  className="filters__search"
                  type="text"
                  placeholder="Hledat podle názvu nebo adresy…"
                  value={searchQuery}
                  onChange={e => onSearchChange(e.target.value)}
                />
              </div>

              <div className="service-panel__list">
                <table className="service-table">
                  <thead>
                    <tr>
                      <th>Firma</th>
                      <th>Adresa</th>
                      <th>Web</th>
                    </tr>
                  </thead>
                  <tbody>
                    {services.length === 0 ? (
                      <tr>
                        <td colSpan={3} className="table-empty">Žádný výsledek</td>
                      </tr>
                    ) : services.map(s => {
                      const webUrl = toAbsoluteUrl(s.web);
                      return (
                        <tr
                          key={s.id}
                          className={selectedService?.id === s.id ? "row-active" : ""}
                          onClick={() => onSelect(s)}
                        >
                          <td>{s.name}</td>
                          <td>{fullAddress(s)}</td>
                          <td className="td-web">
                            {webUrl
                              ? <a href={webUrl} target="_blank" rel="noreferrer"
                                   onClick={e => e.stopPropagation()}>
                                  {s.web.replace(/^https?:\/\//, "")}
                                </a>
                              : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <ServiceDetail service={selectedService} />
            </div>

            {/* RIGHT — map */}
            <div className="layout__right">
              <MapView
                services={services}
                onSelect={onSelect}
              />
            </div>

          </div>
        )}
      </div>
    </main>
  );
}