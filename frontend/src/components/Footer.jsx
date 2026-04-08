import './footer.css';

const Footer = () => {
  return (
    <footer className="school-footer">
      <div className="footer-container">
        {/* Horní sekce se sloupci */}
        <div className="footer-grid">
          
          <div className="footer-col">
            <h3>UŽITEČNÉ ODKAZY</h3>
            <nav>
              <ul>
                <li><a href="https://bakalari.skolahostivar.cz/">Informační systém Bakaláři</a></li>
                <li><a href="#">Info | Office 365</a></li>
                <li className="ms-logo-wrapper">
                  <img 
                    src="https://upload.wikimedia.org/wikipedia/commons/4/44/Microsoft_logo.svg" 
                    alt="Microsoft" 
                  />
                </li>
                <li><a href="#">Výuka – Moodle</a></li>
                <li><a href="#">Objednávání obědů</a></li>
                <li><a href="#">MČ Praha 15</a></li>
                <li><a href="#">Hlavní město Praha</a></li>
              </ul>
            </nav>
          </div>

          <div className="footer-col">
            <h3>ADRESA</h3>
            <address>
              Střední odborná škola automobilní,<br />
              informatiky a Gymnázium<br />
              Weilova 1270/4<br />
              102 00 Praha 10 – Hostivař
            </address>
          </div>

          <div className="footer-col">
            <h3>RYCHLÝ KONTAKT</h3>
            <div className="contact-info">
              <p>Telefon: 242 456 100</p>
              <p>E-mail: <a href="mailto:mailbox@skolahostivar.cz">mailbox@skolahostivar.cz</a></p>
              <p>Datová schránka: 4zxyf53</p>
            </div>
            
            <div className="footer-action-btns">
              <a href="#" className="btn-outline">PROHLÁŠENÍ O PŘÍSTUPNOSTI</a>
              <a href="#" className="btn-outline">GDPR A COOKIES</a>
              <a href="#" className="btn-outline">ETICKÁ LINKA</a>
            </div>
          </div>
        </div>

        <hr className="footer-line" />

        {/* Spodní sekce se sociálními sítěmi */}
        <div className="footer-social-section">
          <h3>SLEDUJTE NÁS</h3>
          <div className="social-links">
            <a href="#" className="s-icon fb" aria-label="Facebook">f</a>
            <a href="#" className="s-icon yt" aria-label="YouTube">▶</a>
            <a href="#" className="s-icon in" aria-label="LinkedIn">in</a>
            <a href="#" className="s-icon ig" aria-label="Instagram">⚓</a>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;