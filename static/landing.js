/* v1.4.20 · Page publique (landing) ORIENTAL24. Aucun script tiers.
   Remplace `renderPublic()` par une page « SaaS logistique » : barre fixe, héros avec cartes animées, trois atouts,
   six services, tarifs par ville filtrables (données `/api/public`), parcours de démarrage, FAQ, bandeau final,
   pied de page complet et bouton WhatsApp flottant (numéro réglé dans Paramètres → Général → « Page publique & contact »).
   Le rendu visuel est porté par landing.css ; les classes `public` / `public-hero` sont conservées pour les parcours QA. */
(function () {
  const CONTACT_KEYS = ['public_whatsapp', 'public_phone', 'public_email', 'public_address', 'public_hours'];
  const DEMO_CONTACT = { public_whatsapp: '+212 6 00 00 00 00', public_phone: '+212 6 00 00 00 00', public_email: 'contact@oriental24.ma', public_address: 'Oujda, région de l’Oriental, Maroc', public_hours: 'Lundi – Vendredi : 9:00 – 18:00\nSamedi : 9:00 – 13:00' };
  const WA_TEXT = 'Bonjour ORIENTAL24, je souhaite des informations sur vos services de livraison.';
  const WA_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.45 1.32 4.95L2 22l5.25-1.38a9.9 9.9 0 0 0 4.79 1.22c5.46 0 9.91-4.45 9.91-9.91S17.5 2 12.04 2zm0 18.15c-1.48 0-2.93-.4-4.2-1.15l-.3-.18-3.12.82.83-3.04-.2-.31a8.2 8.2 0 0 1-1.26-4.38c0-4.54 3.7-8.24 8.25-8.24 4.54 0 8.24 3.7 8.24 8.24 0 4.55-3.7 8.24-8.24 8.24zm4.52-6.16c-.25-.12-1.47-.72-1.69-.81-.23-.08-.39-.12-.56.12-.17.25-.64.81-.78.97-.14.17-.29.19-.54.06-.25-.12-1.05-.39-1.99-1.23-.74-.66-1.23-1.47-1.38-1.72-.14-.25-.02-.38.11-.51.11-.11.25-.29.37-.43.12-.14.17-.25.25-.41.08-.17.04-.31-.02-.43-.06-.12-.56-1.34-.76-1.84-.2-.48-.41-.42-.56-.43h-.48c-.17 0-.43.06-.66.31-.22.25-.86.85-.86 2.07 0 1.22.89 2.4 1.01 2.56.12.17 1.75 2.67 4.23 3.74.59.26 1.05.41 1.41.52.59.19 1.13.16 1.56.1.48-.07 1.47-.6 1.67-1.18.21-.58.21-1.07.14-1.18-.06-.1-.22-.16-.47-.28z"/></svg>';

  let publicContact = {};
  const runtime = () => (typeof RUNTIME !== 'undefined' ? RUNTIME : { demo: true, registration: true, version: '1.4.20' });
  // Valeur affichée : celle enregistrée (même vide = masquée) ; si la clé n'a jamais été réglée, repli de démonstration.
  const contactValue = (k) => (publicContact && Object.prototype.hasOwnProperty.call(publicContact, k) ? String(publicContact[k] || '').trim() : (runtime().demo ? DEMO_CONTACT[k] : ''));
  function waDigits(num) {
    let d = String(num || '').replace(/\D/g, '');
    if (d.startsWith('00')) d = d.slice(2);
    if (d.length === 10 && d.startsWith('0')) d = '212' + d.slice(1);   // numéro marocain saisi au format local
    return d.length >= 8 ? d : '';
  }
  const waHref = () => { const d = waDigits(contactValue('public_whatsapp')); return d ? 'https://wa.me/' + d + '?text=' + encodeURIComponent(WA_TEXT) : ''; };
  const registerAttr = () => (runtime().registration ? 'onclick="renderLogin(true)"' : 'onclick="renderLogin(false)"');

  /* ---------------- Héros : cartes animées ---------------- */
  function showcase(cities) {
    const byName = (n) => cities.find((c) => fold(c.name) === fold(n));
    const city = (n) => esc((byName(n) || cities[['Oujda', 'Nador', 'Berkane', 'Jerada'].indexOf(n)] || { name: n }).name);
    const fee = (n, fallback) => money((byName(n) || {}).fee || fallback);
    // Carte compacte : vignette, puis une ligne titre + élément de droite (badge / montant) et une ligne de détail.
    const simple = (ic, cls, title, sub, right = '') =>
      `<div class="lp-card"><span class="lp-thumb ${cls}">${icon(ic)}</span><span class="lp-card-text"><span class="lp-row"><b>${title}</b>${right}</span>${sub ? `<small>${sub}</small>` : ''}</span></div>`;
    const parcel = (who, place, amount, badge, cls) => simple('box', 'lp-orange', who, `${place} · ${amount} MAD`, `<span class="lp-badge ${cls}">${badge}</span>`);
    const spark = `<svg class="lp-spark" viewBox="0 0 200 56" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id="lp-spark-grad" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#4fd1a5" stop-opacity=".35"/><stop offset="1" stop-color="#4fd1a5" stop-opacity="0"/></linearGradient></defs><path class="lp-spark-fill" d="M0 44 C 18 42, 28 34, 46 36 S 78 46, 98 32 S 136 12, 158 18 S 186 8, 200 6 L200 56 L0 56 Z"/><path d="M0 44 C 18 42, 28 34, 46 36 S 78 46, 98 32 S 136 12, 158 18 S 186 8, 200 6"/></svg>`;
    const a = [
      parcel('Salma A.', city('Oujda'), money(249), 'Livré', 'lp-green'),
      `<div class="lp-card lp-dark"><small>Paiements à la livraison · 7 jours</small><div class="lp-big"><small>MAD</small>${money(12480)}</div><span class="lp-trend">${icon('up')}+ 8,2 % cette semaine</span></div>`,
      simple('truck', 'lp-blue', '12 colis à ramasser', city('Berkane') + ' · Maison Zina'),
      parcel('Imane R.', city('Nador'), money(249), 'En livraison', 'lp-blue'),
      simple('user', 'lp-navy', 'Amine E. · livreur', 'Tournée ' + city('Oujda') + ' · 18 arrêts', `<span class="lp-badge lp-green">Actif</span>`),
    ];
    const b = [
      simple('users', 'lp-green', 'Maison Zina', '28 colis ce mois', `<span class="lp-badge lp-green">Actif</span>`),
      `<div class="lp-card lp-dark"><small>Colis livrés cette semaine</small><div class="lp-big">46</div>${spark}</div>`,
      parcel('Rania F.', city('Jerada'), money(129), 'Programmé', 'lp-orange'),
      simple('checkcircle', 'lp-green', 'Relevé réglé', money(4923.35) + ' MAD · période close', `<span class="lp-badge lp-green">Payé</span>`),
      simple('pin', 'lp-orange', city('Berkane'), 'Ramassage disponible', `<span class="lp-amount">${fee('Berkane', 30)}<small>MAD</small></span>`),
    ];
    const col = (cards, cls) => `<div class="lp-col ${cls}" aria-hidden="true">${cards.join('')}${cards.join('')}</div>`;
    return `<div class="lp-showcase" role="img" aria-label="Aperçu de l’espace client ORIENTAL24 : colis, encaissements et livraisons">${col(a, 'lp-up')}${col(b, 'lp-down')}</div>`;
  }

  /* ---------------- Tarifs par ville ---------------- */
  const fold = (s) => String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  function rateRows(list) {
    if (!list.length) return `<tr><td class="lp-empty" colspan="5">Aucune ville ne correspond à votre recherche.</td></tr>`;
    return list.map((c) =>
      `<tr><td><b>${esc(c.name)}</b></td><td><b>${money(c.fee)}</b><span class="lp-unit">DH</span></td><td>${money(c.return_fee)}<span class="lp-unit">DH</span></td>` +
      `<td>${c.pickup ? '<span class="lp-badge lp-green">Disponible</span>' : '<span class="lp-badge lp-plain">Sur demande</span>'}</td>` +
      `<td><span class="lp-hub">${icon('pin')}${esc(c.region || 'Oriental')}</span></td></tr>`).join('');
  }
  function filterRates() {
    const q = fold(document.getElementById('lp-rate-search')?.value), mode = document.getElementById('lp-rate-mode')?.value || 'all';
    const list = (publicCities || []).filter((c) => (!q || fold(c.name).includes(q)) && (mode !== 'pickup' || c.pickup));
    const body = document.getElementById('lp-rate-body'), count = document.getElementById('lp-rate-count');
    if (body) body.innerHTML = rateRows(list);
    if (count) count.textContent = list.length + (list.length > 1 ? ' villes' : ' ville') + ' sur ' + (publicCities || []).length;
  }
  function toggleRates(btn) {
    const wrap = document.getElementById('lp-rate-wrap');
    if (!wrap) return;
    const collapsed = wrap.classList.toggle('lp-collapsed');
    btn.innerHTML = collapsed ? `Afficher toutes les villes ${icon('down')}` : `Réduire la liste ${icon('up')}`;
    btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
  }

  /* ---------------- Page ---------------- */
  function page() {
    const cities = publicCities || [], r = runtime(), wa = waHref(), nCities = cities.filter((c) => c.delivery !== 0).length, nPickup = cities.filter((c) => c.pickup).length;
    const hours = contactValue('public_hours'), phone = contactValue('public_phone'), email = contactValue('public_email'), address = contactValue('public_address');
    const tel = (p) => 'tel:' + String(p || '').replace(/[^\d+]/g, '');
    const features = [
      ['box', 'Contrôlez vos opérations', 'Colis, ramassages, palettes et stock au même endroit, avec des informations en temps réel pour vous concentrer sur le développement de votre activité.'],
      ['checkcircle', 'Traitez efficacement toutes vos commandes', 'Étiquettes avec QR code, statuts clairs, retours simplifiés : chaque colis suit un parcours maîtrisé jusqu’à la porte de votre client.'],
      ['wallet', 'Gérez vos encaissements', 'Paiement à la livraison, relevés et factures : vos revenus sont suivis avec transparence, du colis livré au règlement.'],
    ];
    const services = [
      ['grid', 'Espace client ORIENTAL24', 'Créez vos colis, imprimez vos étiquettes, suivez chaque livraison et vos encaissements depuis un seul espace, sur ordinateur comme sur mobile.'],
      ['truck', 'Ramassage', 'Programmez un ramassage depuis votre boutique ou votre entrepôt dans les villes desservies ; vos colis entrent aussitôt dans le réseau.'],
      ['clock', 'Livraison en 24 heures', 'Livraison à domicile dans l’Oriental, généralement le lendemain du ramassage, avec suivi d’étapes et notes du livreur.'],
      ['wallet', 'Paiement à la livraison', 'Vos clients paient à la réception. Les montants collectés sont rapprochés et suivis dans votre facturation, frais compris.'],
      ['layers', 'Stock & préparation', 'Confiez-nous vos produits : stock suivi, préparation des commandes et expédition depuis notre hub, sans immobiliser votre équipe.'],
      ['help', 'Support & réclamations', 'Une équipe joignable par téléphone et WhatsApp, et un espace de réclamations avec historique pour chaque colis.'],
    ];
    const steps = [
      ['Jour 0', 'edit', 'Inscrivez-vous et connectez-vous.', 'Créez votre compte partenaire et renseignez votre boutique. Notre équipe valide votre accès.', ''],
      ['Jour 1', 'truck', 'Premier ramassage', 'Ajoutez vos colis dans votre espace et programmez un ramassage dans une ville desservie.', ''],
      ['Jour 2', 'pin', 'Livraison à domicile, en 24 heures', 'Votre livreur ORIENTAL24 livre et encaisse le paiement à la livraison ; vous suivez chaque étape en ligne.', 'lp-accent'],
      ['Jour 3', 'wallet', 'Règlement selon votre relevé', 'Montants encaissés, frais et règlements sont détaillés dans votre rubrique Facturation.', ''],
    ];
    const faq = [
      ['Dans quelles villes livrez-vous ?', 'ORIENTAL24 se développe d’abord dans la région de l’Oriental. Le tableau des tarifs ci-dessus est mis à jour depuis notre espace d’administration et indique les villes ouvertes à la livraison et au ramassage.'],
      ['Quels sont vos tarifs ?', 'Ils dépendent de la ville de destination : consultez le tableau « Nos tarifs de livraison par ville ». Le tarif s’entend par colis livré ; des frais de retour s’appliquent uniquement si le colis revient.'],
      ['Comment demander un ramassage ?', 'Créez votre compte, ajoutez vos colis puis ouvrez la rubrique Ramassages. Choisissez une ville proposant le ramassage, une date et votre adresse.'],
      ['Comment fonctionne le paiement à la livraison ?', 'Vous indiquez le montant à collecter. Une fois le colis livré, l’administration établit un relevé comprenant les montants encaissés et les frais. Le règlement est suivi dans votre rubrique Facturation.'],
      ['Comment suivre un colis ou contacter l’équipe ?', 'Dans votre espace, ouvrez un colis pour consulter son historique. La rubrique Réclamations vous permet d’échanger avec l’équipe ; le bouton WhatsApp de cette page reste disponible pour toute question rapide.'],
      ['Livrez-vous en dehors de l’Oriental ?', 'Notre réseau grandit ville par ville. Si votre destination n’apparaît pas encore, contactez-nous : nous étudions chaque demande de volume ou de palette.'],
    ];
    const navLinks = `<a href="#tarifs">Nos tarifs</a><a href="#services">Services</a><a href="#demarrer">Comment ça marche</a><a href="#faq">FAQ</a>`;
    return `<div class="lp public">
<header class="lp-nav" id="lp-nav"><div class="lp-wrap">
  <a class="lp-brand" href="/" aria-label="ORIENTAL24 accueil"><img class="wordmark" src="/static/wordmark.png" alt="ORIENTAL24"></a>
  <nav class="lp-links" aria-label="Navigation principale">${navLinks}</nav>
  <div class="lp-nav-actions">
    <a class="lp-btn" href="/login">Espace client</a>
    <button type="button" class="lp-btn lp-primary public-register" ${registerAttr()}>${r.registration ? 'S’inscrire' : 'Se connecter'}</button>
    <button type="button" class="lp-burger" aria-label="Ouvrir le menu" aria-expanded="false" aria-controls="lp-mobile-menu" onclick="landingToggleMenu(this)">${icon('menu')}</button>
  </div>
  <div class="lp-mobile-menu" id="lp-mobile-menu">${navLinks.replace(/<a /g, `<a onclick="landingCloseMenu()" `)}<a href="/login">Espace client ${icon('arrow')}</a></div>
</div></header>

<section class="lp-hero public-hero" id="accueil"><div class="lp-wrap">
  <div>
    <span class="lp-pill"><span class="lp-dot"></span>Livraison en 24 heures dans l’Oriental</span>
    <h1>Livraison rapide et fiable pour votre boutique en ligne <em>dans l’Oriental</em></h1>
    <p class="lp-lead">Ramassage, livraison à domicile et paiement à la livraison pour les e-commerçants. Suivez chaque colis et chaque encaissement depuis votre espace client.</p>
    <div class="lp-hero-actions"><button type="button" class="lp-btn lp-primary lp-lg" ${registerAttr()}>Commencer à expédier ${icon('arrow')}</button><a class="lp-btn lp-lg" href="#tarifs">Voir nos tarifs</a></div>
    <div style="margin-top:14px;max-width:560px">${typeof lpTrackForm==="function"?lpTrackForm():""}</div>
    <div class="lp-hero-trust"><span>${icon('checkcircle')}${nCities || '—'} ville${nCities > 1 ? 's' : ''} desservie${nCities > 1 ? 's' : ''}</span><span>${icon('checkcircle')}Paiement à la livraison</span><span>${icon('checkcircle')}Suivi en ligne de vos colis</span></div>
  </div>
  ${showcase(cities)}
</div></section>

<section class="lp-features"><div class="lp-wrap">${features.map(([i, t, p]) => `<article class="lp-feature"><span class="lp-fi">${icon(i)}</span><div><h3>${t}</h3><p>${p}</p></div></article>`).join('')}</div></section>

<section class="lp-section" id="services"><div class="lp-wrap">
  <div class="lp-head"><span class="lp-tag">Services</span><h2>Plus que simplement le ramassage, l’emballage et l’expédition.</h2><p>Vous vous concentrez sur la croissance. Nous assurons la logistique de votre commerce électronique.</p></div>
  <div class="lp-services">${services.map(([i, t, p]) => `<article class="lp-service"><span class="lp-si">${icon(i)}</span><h3>${t}</h3><p>${p}</p></article>`).join('')}</div>
</div></section>

<section class="lp-section lp-rates" id="tarifs"><div class="lp-wrap" id="couverture">
  <div class="lp-head"><span class="lp-tag lp-orange">Villes & tarifs</span><h2>Livraison en 24 heures dans ${nCities || 'les'} villes de l’Oriental</h2><p>Nos tarifs de livraison par ville, tels que configurés dans notre réseau.</p></div>
  <div class="lp-rates-box">
    <div class="lp-filters">
      <label><span class="sr-only">Filtrer par ville</span><input id="lp-rate-search" class="lp-field" type="search" placeholder="Filtrer par ville…" autocomplete="off" oninput="landingFilterRates()"></label>
      <label>Filtrer par<select id="lp-rate-mode" class="lp-field" onchange="landingFilterRates()"><option value="all">Toutes les villes</option><option value="pickup">Ramassage disponible (${nPickup})</option></select></label>
      <span class="lp-count" id="lp-rate-count"></span>
    </div>
    <div class="lp-table-wrap ${cities.length > 8 ? 'lp-collapsed' : ''}" id="lp-rate-wrap"><div class="lp-table-scroll"><table class="lp-table"><thead><tr><th>Ville</th><th>Livraison</th><th>Retour</th><th>Ramassage</th><th>Région</th></tr></thead><tbody id="lp-rate-body">${rateRows(cities)}</tbody></table></div></div>
    <div class="lp-table-actions">${cities.length > 8 ? `<button type="button" class="lp-btn" aria-expanded="false" onclick="landingToggleRates(this)">Afficher toutes les villes ${icon('down')}</button>` : `<button type="button" class="lp-btn" ${registerAttr()}>Devenir partenaire ${icon('arrow')}</button>`}</div>
  </div>
  <p class="lp-rates-note">Tarifs par colis livré, en dirhams. Les frais de retour ne s’appliquent qu’aux colis retournés. Volumes, palettes ou destination absente : contactez-nous pour un devis.${r.demo ? ' Version de démonstration : villes et tarifs initiaux à valider par ORIENTAL24.' : ''}</p>
</div></section>

<section class="lp-section" id="demarrer"><div class="lp-wrap">
  <div class="lp-head"><span class="lp-tag lp-blue">Comment ça marche ?</span><h2>Combien de temps faut-il pour démarrer ?</h2><p>Quelques jours suffisent : de l’inscription à votre premier règlement.</p></div>
  <div class="lp-steps">${steps.map(([d, i, t, p, cls]) => `<article class="lp-step ${cls}"><span class="lp-node"></span><div class="lp-day">${d.toUpperCase()}</div><span class="lp-si">${icon(i)}</span><h3>${t}</h3><p>${p}</p></article>`).join('')}</div>
</div></section>

<section class="lp-section" id="faq"><div class="lp-wrap">
  <div class="lp-head"><span class="lp-tag lp-green">FAQ</span><h2>On vous répond. Tout simplement.</h2></div>
  <div class="lp-faq">${faq.map(([q, a]) => `<details><summary>${q}<span class="lp-plus">${icon('plus')}</span></summary><p>${a}</p></details>`).join('')}</div>
</div></section>

<section class="lp-cta"><div class="lp-wrap"><div class="lp-cta-box">
  <div><h2>Prêt à livrer plus proche de vos clients ?</h2><p>Rejoignez les boutiques qui expédient avec ORIENTAL24 dans l’Oriental : ramassage, livraison en 24 heures et paiement à la livraison.</p></div>
  <div class="lp-cta-actions"><button type="button" class="lp-btn lp-primary lp-lg" ${registerAttr()}>${r.registration ? 'Créer mon compte' : 'Accéder à mon espace'} ${icon('arrow')}</button>${wa ? `<a class="lp-btn lp-lg" href="${wa}" target="_blank" rel="noopener">${icon('phone')}Parler à un conseiller</a>` : `<a class="lp-btn lp-lg" href="/login">Espace client</a>`}</div>
</div></div></section>

<footer class="lp-footer"><div class="lp-wrap">
  <div class="lp-footer-grid">
    <div class="lp-footer-about"><a class="lp-brand" href="/" aria-label="ORIENTAL24 accueil"><img class="wordmark" src="/static/wordmark.png" alt="ORIENTAL24"></a><div><span class="lp-lang">${icon('globe')}Français</span></div><p>Nous vous proposons le service logistique le plus simple de la région et la meilleure expérience de livraison pour vos clients.</p></div>
    <div><h4>Nos services</h4><ul><li><a href="#services">Ramassage & livraison</a></li><li><a href="#tarifs">Nos tarifs</a></li><li><a href="#services">Paiement à la livraison</a></li><li><a href="/login">Suivi de livraison</a></li></ul></div>
    <div><h4>Plus d’aide</h4><ul><li><a href="#faq">FAQ</a></li><li><a href="/login">Réclamations</a></li>${wa ? `<li><a class="lp-live" href="${wa}" target="_blank" rel="noopener">Chat WhatsApp</a></li>` : ''}${hours ? `<li><span style="white-space:pre-line">${esc(hours)}</span></li>` : ''}</ul></div>
    <div><h4>Contactez-nous</h4><ul>${email ? `<li>${icon('mail')}<a href="mailto:${esc(email)}">${esc(email)}</a></li>` : ''}${phone ? `<li>${icon('phone')}<a href="${esc(tel(phone))}">${esc(phone)}</a></li>` : ''}${address ? `<li>${icon('pin')}<span>${esc(address)}</span></li>` : ''}</ul></div>
  </div>
  <div class="lp-footer-bottom"><span>© ${new Date().getFullYear()} ORIENTAL24 · Livraison à domicile dans l’Oriental.</span><span><a href="/login">Espace client</a> · <a href="#accueil">Haut de page</a> · v${esc(String(r.version || '1.4.20'))}</span></div>
</div></footer>
${wa ? `<a class="lp-wa" href="${wa}" target="_blank" rel="noopener" aria-label="Écrire à ORIENTAL24 sur WhatsApp">${WA_SVG}<span class="lp-wa-text">WhatsApp<small>Réponse rapide</small></span></a>` : ''}
</div>`;
  }

  function onScroll() { const nav = document.getElementById('lp-nav'); if (nav) nav.classList.toggle('is-scrolled', window.scrollY > 6); }
  window.landingFilterRates = filterRates;
  window.landingToggleRates = toggleRates;
  window.landingToggleMenu = function (btn) { const nav = document.getElementById('lp-nav'); const open = nav.classList.toggle('is-open'); btn.setAttribute('aria-expanded', open ? 'true' : 'false'); btn.setAttribute('aria-label', open ? 'Fermer le menu' : 'Ouvrir le menu'); };
  window.landingCloseMenu = function () { const nav = document.getElementById('lp-nav'); if (nav) nav.classList.remove('is-open'); };

  let ready = false;
  // Typographie française : espace insécable devant « ? », « : » et « ; » (le « ? » ne reste jamais seul en fin de ligne).
  const frenchSpaces = (html) => html.replace(/ ([?:;])/g, '\u00a0$1');
  function renderNow() { const root = document.getElementById('root'); if (!root) return; root.innerHTML = frenchSpaces(page()); filterRates(); onScroll(); }
  renderPublic = async function () {
    if (typeof closeWorkspaceMenu === 'function') closeWorkspaceMenu();
    S = null;
    document.title = 'ORIENTAL24 — Livraison rapide et fiable dans l’Oriental';
    try { const d = await api('/public'); publicCities = d.cities || []; publicContact = d.contact || {}; } catch (e) { publicCities = []; publicContact = {}; }
    ready = true; renderNow();
  };
  addEventListener('scroll', onScroll, { passive: true });
  /* Course à l'amorçage : `boot()` (app.js) a lancé l'ancienne `renderPublic` avant le chargement de ce fichier ; son rendu
     peut donc arriver après le nôtre. On relance la page publique ici et, si l'ancien balisage réapparaît, on le remplace
     aussitôt (MutationObserver = micro-tâche, avant tout affichage). */
  const rootNode = document.getElementById('root');
  if (rootNode) new MutationObserver(() => { if (ready && rootNode.querySelector(':scope > .public') && !rootNode.querySelector(':scope > .lp')) renderNow(); }).observe(rootNode, { childList: true });
  if (typeof ORIENTAL24_RUNTIME === 'object' && !['/app', '/login'].includes(location.pathname)) renderPublic();

  /* ---------------- Paramètres → Général : « Page publique & contact » ---------------- */
  const landingBaseSettings = settingsView;
  settingsView = function () {
    let html = landingBaseSettings.apply(this, arguments);
    if (typeof settingsTab === 'undefined' || settingsTab !== 'general' || typeof S === 'undefined' || !S) return html;
    const v = (k) => (S.settings && S.settings[k]) || '';
    const block = `<div class="lp-settings" style="border-top:1px solid var(--line);padding-top:20px;margin-top:22px"><h3 style="font-size:14px">Page publique & contact</h3><p class="form-hint" style="margin:6px 0 14px">Affichés sur la page d’accueil publique : bouton WhatsApp flottant, pied de page « Contactez-nous » et horaires. Laissez vide pour masquer un élément (en version de démonstration, des coordonnées fictives s’affichent alors par défaut).</p><div class="form-grid">${input('public_whatsapp', 'Numéro WhatsApp (bouton flottant)', v('public_whatsapp'), 'tel', false, 'placeholder="+212 6 00 00 00 00" maxlength="25"')}${input('public_phone', 'Téléphone affiché', v('public_phone'), 'tel', false, 'maxlength="25"')}${input('public_email', 'E-mail de contact', v('public_email'), 'email', false, 'maxlength="120"')}${input('public_address', 'Adresse', v('public_address'), 'text', false, 'maxlength="200"')}</div>${textarea('public_hours', 'Horaires (une ligne par plage)', v('public_hours'))}</div>`;
    const i = html.indexOf('<div class="form-actions"');
    return i > -1 ? html.slice(0, i) + block + html.slice(i) : html;
  };
})();
