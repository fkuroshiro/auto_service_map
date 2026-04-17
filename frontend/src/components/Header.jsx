import "./header.css";

const BACK_URL = import.meta.env.VITE_BACK_URL ?? "https://skolahostivar.cz/partneri-a-praxe/";

export default function Header() {
  return (
    <header className="site-header">
      
      {/* ── Hero s bg fotkou auta ── */}
      <div className="site-header__hero">
        <div className="site-header__hero-overlay" />
        <div className="site-header__container site-header__hero-inner">
          <a href={BACK_URL} className="site-header__back">
            <span className="site-header__back-circle">
              <svg width="15" height="15" viewBox="0 0 18 18" fill="none">
                <path d="M11.5 3.5L6 9L11.5 14.5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </span>
            <span>Zpět</span>
          </a>
          <h3 className="site-header__eyebrow z-10">Informace</h3>
          <h1 className="site-header__title z-10">
            Praxe žáků<br />autooborů
          </h1>
        </div>
      </div>

    </header>
  );
}