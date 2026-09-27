/* v1.4.19 · Habillage professionnel du cadre (barre latérale + barre supérieure). Aucun script tiers.
   - Bas de barre latérale : entrée « Aide & réclamations », carte du compte connecté (avatar, nom, rôle, déconnexion), version.
     Hauteur identique en mode compact et déplié : la barre « intelligente » (v1.4.18) ne bouge jamais au survol.
   - Barre supérieure : ombre légère dès que la page est défilée, libellés d'accessibilité.
   - Thème de la barre : « Bleu nuit » (défaut) ou « Claire », au choix de l'utilisateur dans Mon profil → Apparence ;
     préférence conservée dans le navigateur (localStorage), appliquée avant le premier rendu (aucun clignotement).
   Le rendu visuel est porté par ui-pro.css ; ce script n'ajoute que du balisage et une classe sur <html>. */
(function () {
  const THEMES = { navy: 'Bleu nuit', light: 'Claire' }, KEY = 'o24.sidebarTheme';
  function readTheme() { try { const t = localStorage.getItem(KEY); return THEMES[t] ? t : 'navy'; } catch (e) { return 'navy'; } }
  function currentTheme() { return document.documentElement.classList.contains('sb-light') ? 'light' : 'navy'; }
  function applyTheme(t) { document.documentElement.classList.toggle('sb-light', t === 'light'); }
  function setSidebarTheme(t) {
    if (!THEMES[t]) return;
    applyTheme(t);
    try { localStorage.setItem(KEY, t); } catch (e) { /* navigation privée : le choix vaut pour la session */ }
    document.querySelectorAll('.theme-option').forEach((b) => { const on = b.dataset.theme === t; b.classList.toggle('is-selected', on); b.setAttribute('aria-checked', on ? 'true' : 'false'); });
    if (typeof toast === 'function') toast('Thème « ' + THEMES[t] + ' » appliqué');
  }
  function appearanceCard() {
    const t = currentTheme();
    const option = (id, desc) =>
      `<button type="button" class="theme-option${t === id ? ' is-selected' : ''}" role="radio" aria-checked="${t === id}" data-theme="${id}" onclick="setSidebarTheme('${id}')">` +
        `<span class="theme-thumb theme-thumb-${id}" aria-hidden="true"><i></i><em></em></span>` +
        `<span class="theme-text"><b>${THEMES[id]}</b><small>${desc}</small></span>` +
        `<span class="theme-check" aria-hidden="true">${icon('check')}</span>` +
      `</button>`;
    return `<section class="card appearance-card" id="appearance-card"><div class="card-head"><div><h3>Apparence</h3><p>Habillage de la barre latérale. Préférence enregistrée sur cet appareil (navigateur), sans effet sur les autres utilisateurs.</p></div></div>` +
      `<div class="theme-options" role="radiogroup" aria-label="Thème de la barre latérale">${option('navy', 'Identité ORIENTAL24 — par défaut')}${option('light', 'Barre blanche, accent orange')}</div></section>`;
  }
  function mountSidebar() {
    const side = document.querySelector('#root .sidebar'), bottom = side && side.querySelector('.sidebar-bottom');
    if (!bottom || typeof S === 'undefined' || !S || !S.user) return;
    // Version affichée : celle du serveur si complète (x.y.z), sinon celle de cette livraison (fichier HTML autonome).
    const u = S.user, version = (typeof RUNTIME !== 'undefined' && /^\d+\.\d+\.\d+/.test(String(RUNTIME.version || ''))) ? RUNTIME.version : '1.6.2';
    bottom.classList.add('sidebar-bottom-pro');
    bottom.innerHTML =
      `<button type="button" class="nav-item sidebar-aid" title="Aide &amp; réclamations" onclick="navigate('tickets')">${icon('help')}<span>Aide &amp; réclamations</span></button>` +
      `<div class="sidebar-user" role="group" aria-label="Compte connecté">` +
        `<button type="button" class="sidebar-user-main" title="${esc(u.name)} · Mon profil" aria-label="Mon profil" onclick="navigate('profile')">` +
          `<span class="avatar sidebar-avatar" aria-hidden="true">${initials(u.name)}</span>` +
          `<span class="sidebar-user-text"><b dir="auto">${esc(u.name)}</b><small>${roleName(u.role)}</small></span>` +
        `</button>` +
        `<button type="button" class="icon-btn sidebar-logout" title="Se déconnecter" aria-label="Se déconnecter" onclick="logout()">${icon('logout')}</button>` +
      `</div>` +
      `<div class="sidebar-foot"><span>ORIENTAL24 · v${esc(String(version))}</span><span>${(typeof RUNTIME !== 'undefined' && RUNTIME.demo) ? 'DÉMO' : 'PROD'}</span></div>`;
  }
  function mountTopbar() {
    const top = document.querySelector('#root .topbar');
    if (!top) return;
    top.classList.add('topbar-pro');
    const search = top.querySelector('.global-search');
    if (search) { search.setAttribute('aria-label', 'Rechercher un colis (raccourci ⌘/Ctrl K)'); search.type = 'button'; }
    const lang = top.querySelector('.lang');
    if (lang) { lang.setAttribute('title', 'Interface en français'); lang.setAttribute('aria-label', 'Langue : français'); }
    const profile = top.querySelector('.top-profile');
    if (profile) profile.setAttribute('aria-label', 'Mon profil');
    onScroll();
  }
  function onScroll() {
    const top = document.querySelector('#root .topbar.topbar-pro');
    if (top) top.classList.toggle('is-scrolled', window.scrollY > 4);
  }
  function mount() { mountSidebar(); mountTopbar(); }

  applyTheme(readTheme());
  const uiProBaseShell = shell;
  shell = function () { const out = uiProBaseShell.apply(this, arguments); mount(); return out; };
  const uiProBaseProfile = profileView;
  profileView = function () { return uiProBaseProfile.apply(this, arguments) + appearanceCard(); };
  addEventListener('scroll', onScroll, { passive: true });
  if (document.querySelector('#root .sidebar')) mount();
  window.setSidebarTheme = setSidebarTheme;
  window.uiProMount = mount;   // utile aux parcours QA / injection
})();
