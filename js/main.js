/* ============================================
   IISS "Giudici Saetta e Livatino" - Main JS
   Accessibile WCAG 2.1 AA
   ============================================ */

document.addEventListener('DOMContentLoaded', () => {

  // --- Sticky Navbar ---
  const navbar = document.querySelector('.navbar');
  if (navbar) {
    window.addEventListener('scroll', () => {
      navbar.classList.toggle('scrolled', window.scrollY > 20);
    });
  }

  // --- Hamburger Menu ---
  const hamburger = document.querySelector('.hamburger');
  const navMenu = document.querySelector('.nav-menu');
  const overlay = document.querySelector('.mobile-overlay');

  function closeMenu() {
    hamburger?.classList.remove('active');
    navMenu?.classList.remove('open');
    overlay?.classList.remove('active');
    if (hamburger) hamburger.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
  }

  function openMenu() {
    hamburger?.classList.add('active');
    navMenu?.classList.add('open');
    overlay?.classList.add('active');
    if (hamburger) hamburger.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
    // Focus primo link nel menu
    const firstLink = navMenu?.querySelector('.nav-link');
    if (firstLink) firstLink.focus();
  }

  hamburger?.addEventListener('click', () => {
    if (navMenu?.classList.contains('open')) {
      closeMenu();
    } else {
      openMenu();
    }
  });

  overlay?.addEventListener('click', closeMenu);

  // --- Dropdown Toggle (Accessibile) ---
  const dropdownParents = document.querySelectorAll('.nav-item.has-dropdown');

  function closeAllDropdowns(except) {
    dropdownParents.forEach(item => {
      if (item !== except) {
        item.classList.remove('active');
        const btn = item.querySelector('.nav-link[aria-expanded]');
        if (btn) btn.setAttribute('aria-expanded', 'false');
      }
    });
  }

  function openDropdown(item) {
    closeAllDropdowns(item);
    item.classList.add('active');
    const btn = item.querySelector('.nav-link[aria-expanded]');
    if (btn) btn.setAttribute('aria-expanded', 'true');
  }

  function closeDropdown(item) {
    item.classList.remove('active');
    const btn = item.querySelector('.nav-link[aria-expanded]');
    if (btn) btn.setAttribute('aria-expanded', 'false');
  }

  function toggleDropdown(item) {
    if (item.classList.contains('active')) {
      closeDropdown(item);
    } else {
      openDropdown(item);
    }
  }

  dropdownParents.forEach(item => {
    const trigger = item.querySelector('.nav-link');
    const dropdown = item.querySelector('.dropdown');

    // Click/Enter/Space apre/chiude il dropdown
    trigger?.addEventListener('click', (e) => {
      e.preventDefault();
      toggleDropdown(item);
    });

    // Tastiera sul trigger
    trigger?.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        openDropdown(item);
        const firstItem = dropdown?.querySelector('a');
        if (firstItem) firstItem.focus();
      } else if (e.key === 'Escape') {
        closeDropdown(item);
        trigger.focus();
      }
    });

    // Navigazione tastiera dentro il dropdown
    dropdown?.addEventListener('keydown', (e) => {
      const items = [...dropdown.querySelectorAll('a')];
      const currentIndex = items.indexOf(document.activeElement);

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        const next = currentIndex < items.length - 1 ? currentIndex + 1 : 0;
        items[next]?.focus();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (currentIndex <= 0) {
          trigger.focus();
          closeDropdown(item);
        } else {
          items[currentIndex - 1]?.focus();
        }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        closeDropdown(item);
        trigger.focus();
      } else if (e.key === 'Tab') {
        // Chiudi dropdown quando si esce con Tab
        closeDropdown(item);
      }
    });
  });

  // Close dropdowns when clicking outside
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.nav-item.has-dropdown')) {
      closeAllDropdowns();
    }
  });

  // Close on Escape key anywhere
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeAllDropdowns();
      if (navMenu?.classList.contains('open')) {
        closeMenu();
        hamburger?.focus();
      }
    }
  });

  // Close mobile menu on dropdown link click
  document.querySelectorAll('.dropdown a').forEach(link => {
    link.addEventListener('click', () => {
      if (window.innerWidth <= 768) {
        closeMenu();
        closeAllDropdowns();
      }
    });
  });

  // --- Caricamento Notizie da JSON ---
  const newsGrid = document.getElementById('news-grid');
  const VISIBLE_COUNT = 6;
  const arrowSvg = '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>';
  const calendarSvg = '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>';

  const categoryLabels = {
    avviso: 'Avviso', progetto: 'Progetto', erasmus: 'Erasmus+',
    istituto: 'Istituto', graduatoria: 'Graduatoria', sindacale: 'Sindacale'
  };

  function renderNewsCard(notizia, index) {
    const isHidden = index >= VISIBLE_COUNT ? ' hidden' : '';
    const linksHtml = notizia.links.map((link, i) => {
      const isExternal = link.url.startsWith('http');
      const targetAttr = isExternal ? ' target="_blank" rel="noopener"' : '';
      const srHint = isExternal ? '<span class="sr-only"> (si apre in una nuova finestra)</span>' : '';
      return `${i > 0 ? '<br>' : ''}<a href="${link.url}"${targetAttr} class="news-link">${link.testo}${srHint} ${arrowSvg}</a>`;
    }).join('');
    return `<article class="news-card fade-in${isHidden}">
        <div class="news-card-body">
          <span class="news-tag ${notizia.categoria}">${categoryLabels[notizia.categoria] || notizia.categoria}</span>
          <h3>${notizia.titolo}</h3>
          <div class="news-date"><time>${calendarSvg} ${notizia.data}</time></div>
          <p>${notizia.descrizione}</p>
          ${linksHtml}
        </div>
      </article>`;
  }

  if (newsGrid) {
    fetch('data/notizie.json')
      .then(res => res.json())
      .then(notizie => {
        newsGrid.innerHTML = notizie.map((n, i) => renderNewsCard(n, i)).join('');

        // Toggle mostra/nascondi
        const hiddenCards = newsGrid.querySelectorAll('.news-card.hidden');
        const toggleWrap = document.getElementById('news-toggle-wrap');
        const toggleBtn = document.getElementById('newsToggle');

        if (toggleBtn && hiddenCards.length > 0) {
          toggleWrap.style.display = '';
          toggleBtn.textContent = `Mostra tutte le notizie (altre ${hiddenCards.length})`;
          toggleBtn.setAttribute('aria-expanded', 'false');
          let expanded = false;

          toggleBtn.addEventListener('click', () => {
            expanded = !expanded;
            hiddenCards.forEach(card => card.classList.toggle('hidden', !expanded));
            toggleBtn.textContent = expanded ? 'Mostra meno notizie' : `Mostra tutte le notizie (altre ${hiddenCards.length})`;
            toggleBtn.setAttribute('aria-expanded', String(expanded));
          });
        }

        // Attiva fade-in sulle nuove card
        if ('IntersectionObserver' in window) {
          const obs = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
              if (entry.isIntersecting) { entry.target.classList.add('visible'); obs.unobserve(entry.target); }
            });
          }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });
          newsGrid.querySelectorAll('.fade-in').forEach(el => obs.observe(el));
        } else {
          newsGrid.querySelectorAll('.fade-in').forEach(el => el.classList.add('visible'));
        }
      })
      .catch(() => {
        newsGrid.innerHTML = '<p role="alert" style="text-align:center;color:#888">Impossibile caricare le notizie.</p>';
      });
  }

  // --- Fade-In on Scroll (IntersectionObserver) ---
  const fadeElements = document.querySelectorAll('.fade-in');

  if ('IntersectionObserver' in window && fadeElements.length > 0) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, {
      threshold: 0.1,
      rootMargin: '0px 0px -40px 0px'
    });

    fadeElements.forEach(el => observer.observe(el));
  } else {
    // Fallback: show all elements immediately
    fadeElements.forEach(el => el.classList.add('visible'));
  }

  // --- Rispetta prefers-reduced-motion ---
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    document.querySelectorAll('.fade-in').forEach(el => {
      el.classList.add('visible');
      el.style.transition = 'none';
    });
  }

  // --- Anno Scolastico automatico (cambia ogni 1 settembre) ---
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth(); // 0-indexed: 0=Jan, 8=Sep
  const startYear = month >= 8 ? year : year - 1;
  const endYear = startYear + 1;

  const annoEl = document.getElementById('anno-scolastico');
  if (annoEl) {
    annoEl.textContent = `Anno Scolastico ${startYear}/${endYear}`;
  }

  const copyrightEl = document.getElementById('copyright-year');
  if (copyrightEl) {
    copyrightEl.textContent = year;
  }

  // --- Smooth scroll for anchor links ---
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', (e) => {
      const targetId = anchor.getAttribute('href');
      if (targetId === '#') return;
      const target = document.querySelector(targetId);
      if (target) {
        e.preventDefault();
        const navHeight = navbar?.offsetHeight || 70;
        const y = target.getBoundingClientRect().top + window.scrollY - navHeight;
        window.scrollTo({ top: y, behavior: 'smooth' });
        // Set focus on target for accessibility
        target.setAttribute('tabindex', '-1');
        target.focus({ preventScroll: true });
        // Close mobile menu if open
        closeMenu();
      }
    });
  });

  // --- Cookie Consent Banner ---
  initCookieBanner();

});


// ============================================================
// COOKIE CONSENT BANNER (GDPR / Garante Privacy)
// ============================================================
function initCookieBanner() {
  // Non mostrare nel pannello admin
  if (window.location.pathname.includes('admin.html')) return;

  const COOKIE_KEY = 'cookie_consent';
  const consent = localStorage.getItem(COOKIE_KEY);

  // Inserisci link "Preferenze cookie" nel footer
  addCookieFooterLink();

  // Se il consenso esiste già, non mostrare il banner
  if (consent) return;

  // Crea e mostra il banner
  const banner = createCookieBanner();
  document.body.appendChild(banner);

  // Mostra con animazione (dopo un frame per attivare la transizione CSS)
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      banner.classList.add('visible');
    });
  });

  function createCookieBanner() {
    const div = document.createElement('div');
    div.className = 'cookie-banner';
    div.setAttribute('role', 'dialog');
    div.setAttribute('aria-label', 'Informativa sui cookie');
    div.innerHTML = `
      <div class="cookie-banner-inner">
        <h3>Rispettiamo la tua privacy</h3>
        <p>
          Questo sito utilizza cookie tecnici necessari al funzionamento e servizi di terze parti
          (Google Fonts per la tipografia). Non utilizziamo cookie di profilazione o pubblicitari.
          Per maggiori informazioni consulta la nostra <a href="${getRelPath()}pagine/privacy.html">Privacy Policy</a>.
        </p>
        <div class="cookie-banner-actions">
          <button class="cookie-btn cookie-btn-accept" id="cookieAcceptAll">Accetta e Chiudi</button>
          <button class="cookie-btn cookie-btn-reject" id="cookieRejectAll">Continua senza accettare</button>
          <button class="cookie-btn cookie-btn-customize" id="cookieCustomize" aria-expanded="false">Personalizza</button>
        </div>
        <div class="cookie-details" id="cookieDetails">
          <div class="cookie-category">
            <div class="cookie-category-info">
              <div class="cookie-category-name">Cookie tecnici necessari</div>
              <div class="cookie-category-desc">Indispensabili per il funzionamento del sito (sessione area riservata). Non possono essere disattivati.</div>
            </div>
            <label class="cookie-toggle">
              <input type="checkbox" checked disabled>
              <span class="cookie-toggle-slider"></span>
            </label>
          </div>
          <div class="cookie-category">
            <div class="cookie-category-info">
              <div class="cookie-category-name">Servizi di terze parti</div>
              <div class="cookie-category-desc">Google Fonts per il caricamento dei caratteri tipografici. Nessun dato personale viene raccolto.</div>
            </div>
            <label class="cookie-toggle">
              <input type="checkbox" id="cookieThirdParty" checked>
              <span class="cookie-toggle-slider"></span>
            </label>
          </div>
          <button class="cookie-btn cookie-btn-save" id="cookieSavePrefs">Salva preferenze</button>
        </div>
      </div>
    `;
    return div;
  }

  function getRelPath() {
    // Determina il percorso relativo alla root in base alla posizione della pagina
    const path = window.location.pathname;
    if (path.includes('/pagine/')) return '../';
    return '';
  }

  function saveConsent(level) {
    const data = {
      level: level, // 'all', 'necessary', 'custom'
      thirdParty: level === 'all' || (level === 'custom' && document.getElementById('cookieThirdParty')?.checked),
      timestamp: new Date().toISOString()
    };
    localStorage.setItem(COOKIE_KEY, JSON.stringify(data));
    closeBanner();
  }

  function closeBanner() {
    banner.classList.remove('visible');
    setTimeout(() => banner.remove(), 400);
  }

  // Event listeners
  document.addEventListener('click', (e) => {
    if (e.target.id === 'cookieAcceptAll') {
      saveConsent('all');
    } else if (e.target.id === 'cookieRejectAll') {
      saveConsent('necessary');
    } else if (e.target.id === 'cookieCustomize') {
      const details = document.getElementById('cookieDetails');
      const expanded = details.classList.toggle('visible');
      e.target.setAttribute('aria-expanded', String(expanded));
    } else if (e.target.id === 'cookieSavePrefs') {
      saveConsent('custom');
    }
  });
}

function addCookieFooterLink() {
  const footerBottom = document.querySelector('.footer-bottom');
  if (!footerBottom) return;

  // Trova il div con i link Privacy/Accessibilita'
  const linksDiv = footerBottom.querySelectorAll('div')[1];
  if (!linksDiv) return;

  // Controlla se il link esiste già
  if (linksDiv.querySelector('.cookie-preferences-link')) return;

  const separator = document.createTextNode(' \u00B7 ');
  const btn = document.createElement('button');
  btn.className = 'cookie-preferences-link';
  btn.textContent = 'Preferenze cookie';
  btn.addEventListener('click', () => {
    // Resetta il consenso e mostra il banner
    localStorage.removeItem('cookie_consent');
    initCookieBanner();
  });

  linksDiv.appendChild(separator);
  linksDiv.appendChild(btn);
}
