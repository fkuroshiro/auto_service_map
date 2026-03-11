import { useMemo, useState, useEffect } from "react";
import Main from "./components/Main.jsx";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:5000/api/map-data";

export default function App() {
  const [services, setServices]               = useState([]);
  const [loading, setLoading]                 = useState(true);
  const [error, setError]                     = useState(null);
  const [selectedService, setSelectedService] = useState(null);
  const [searchQuery, setSearchQuery]         = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const res  = await fetch(API_URL);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        if (cancelled) return;

        const normalized = data.map((item, i) => ({
          id:      i + 1,
          name:    item.name,
          address: item.address.split(",")[0]?.trim() || item.address,
          city:    item.address.split(",")[1]?.trim() || "",
          web:     item.web || null,
          lat:     item.lat,
          lng:     item.lng,
        }));

        setServices(normalized);
        setSelectedService(prev => prev ?? normalized[0] ?? null);
        setError(null);
      } catch {
        if (!cancelled) setError("Nepodařilo se načíst data ze serveru.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    const iv = setInterval(load, 60 * 60 * 1000);
    return () => { cancelled = true; clearInterval(iv); };
  }, []);

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return services;
    return services.filter(s =>
      `${s.name} ${s.city} ${s.address}`.toLowerCase().includes(q)
    );
  }, [services, searchQuery]);

  const safeSelected = filtered.some(s => s.id === selectedService?.id)
    ? selectedService
    : filtered[0] ?? null;

  return (
    <div className="page">
      <Main
        services={filtered}
        selectedService={safeSelected}
        onSelect={setSelectedService}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        loading={loading}
        error={error}
      />
    </div>
  );
}