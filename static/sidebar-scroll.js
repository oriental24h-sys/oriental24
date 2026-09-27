/* v1.4.18 · Barre latérale « intelligente » (ordinateur, ≥ 721 px). Aucun script tiers.
   Principe : la barre est `position: sticky` (voir sidebar-scroll.css) ; elle n'a plus d'ascenseur interne.
   Ce script choisit seulement, selon le sens du défilement, le bord auquel elle se cale :
     - on descend  → seuil `top = hauteurÉcran − hauteurBarre` : elle suit la page puis se cale en bas ;
     - on remonte  → elle est libérée (position naturelle = position visible), suit la page, puis se cale en haut.
   Le `margin-top` sert uniquement à figer la position naturelle au moment d'un changement de sens : aucun saut.
   Si la barre tient dans l'écran, elle reste simplement calée en haut. Mobile : le tiroir `position: fixed`
   reste inchangé, ce script ne touche à rien. */
(function () {
  const DESKTOP = '(min-width:721px)';
  const desktop = () => matchMedia(DESKTOP).matches;
  const root = () => document.getElementById('root');
  let side = null, col = null, observer = null;
  let lastY = 0, mode = 'top', pinTop = 0, margin = 0;

  function apply(top, m) {
    m = Math.max(0, m);
    if (Math.abs(top - pinTop) > 0.01 || side.style.top === '') { pinTop = top; side.style.top = top + 'px'; }
    if (Math.abs(m - margin) > 0.01 || side.style.marginTop === '') { margin = m; side.style.marginTop = m + 'px'; }
  }
  function clear() { if (side) { side.style.top = ''; side.style.marginTop = ''; } mode = 'top'; pinTop = 0; margin = 0; }
  const colTop = () => col.getBoundingClientRect().top + window.scrollY;

  /* Libère la barre : sa position naturelle devient sa position visible (décalée de `shift` pour rattraper le
     défilement déjà appliqué par le navigateur), bornée entre le seuil bas et le haut de l'écran. Le seuil
     retenu n'est jamais au-dessus de cette position : rien ne saute. */
  function freeAt(rect, y, bottomTop, shift) {
    const low = Math.min(bottomTop, rect.top);
    const t = Math.min(0, Math.max(low, rect.top + shift));
    apply(Math.min(bottomTop, t), y + t - colTop());
    mode = 'bottom';
  }

  function update(resized) {
    if (!side || !col || !side.isConnected) return;
    if (!desktop()) { clear(); lastY = window.scrollY; return; }
    const y = window.scrollY, vh = window.innerHeight, sH = side.offsetHeight, prevY = lastY;
    lastY = y;
    if (sH <= vh) { apply(0, 0); mode = 'top'; return; }                       // tient dans l'écran : calée en haut
    const rect = side.getBoundingClientRect(), bottomTop = vh - sH;
    if (mode === 'top') {
      if (y > prevY) freeAt(rect, y, bottomTop, prevY - y);                    // on quitte le haut : elle suit la page
      return;
    }
    if (rect.top > 0.5 || (y < prevY && rect.top >= 0)) { apply(0, 0); mode = 'top'; return; }   // son haut est revenu
    if (resized) { freeAt(rect, y, bottomTop, 0); return; }                    // hauteur changée (survol, rôle, écran)
    const natural = margin + colTop() - y;
    if (pinTop < bottomTop - 0.5 && natural >= bottomTop - 0.5) apply(bottomTop, margin);   // seuil périmé : rafraîchi sans bouger
    if (y < prevY && rect.top <= pinTop + 1) freeAt(rect, y, bottomTop, prevY - y);         // calée en bas : libérée, elle suit la page
  }

  /* Clavier : le sens du défilement est connu avant qu'il ait lieu ; on libère la barre tout de suite. */
  function prepare(dir) {
    if (!side || !col || !side.isConnected || !desktop()) return;
    const vh = window.innerHeight, sH = side.offsetHeight;
    if (sH <= vh) return;
    const rect = side.getBoundingClientRect(), y = window.scrollY;
    if (dir === 'down' && mode === 'top') freeAt(rect, y, vh - sH, 0);
    else if (dir === 'up' && mode === 'bottom' && rect.top < 0 && rect.top <= pinTop + 1) freeAt(rect, y, vh - sH, 0);
  }
  const editable = (t) => !!t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable);
  function onKey(e) {
    if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || editable(e.target)) return;
    if (['ArrowDown', 'PageDown', 'End'].includes(e.key) || (e.key === ' ' && !e.shiftKey)) prepare('down');
    else if (['ArrowUp', 'PageUp', 'Home'].includes(e.key) || (e.key === ' ' && e.shiftKey)) prepare('up');
  }

  /* Navigation au clavier dans le menu : un élément hors écran devient visible en faisant défiler la page. */
  function onFocus(e) {
    if (!desktop() || !side || !col || !side.isConnected) return;
    const t = e.target.getBoundingClientRect(), vh = window.innerHeight;
    if (t.top >= 0 && t.bottom <= vh) return;
    const sH = side.offsetHeight;
    if (sH > vh) freeAt(side.getBoundingClientRect(), window.scrollY, vh - sH, 0);
    e.target.scrollIntoView({ block: 'nearest' });
  }

  function unmount() {
    if (observer) observer.disconnect();
    observer = null; side = null; col = null; mode = 'top'; pinTop = 0; margin = 0;
    root()?.classList.remove('sticky-nav');
  }
  function mount() {
    const r = root(), aside = r && r.querySelector(':scope > .sidebar, :scope > .sidebar-col > .sidebar');
    if (!aside) { unmount(); return; }
    if (observer) observer.disconnect();
    side = aside;
    col = side.parentElement.classList.contains('sidebar-col') ? side.parentElement : null;
    if (!col) { col = document.createElement('div'); col.className = 'sidebar-col'; side.parentNode.insertBefore(col, side); col.appendChild(side); }
    r.classList.add('sticky-nav');
    const bottom = side.querySelector('.sidebar-bottom');
    if (bottom && !bottom.querySelector('.sidebar-help-compact')) bottom.insertAdjacentHTML('afterbegin', `<button type="button" class="nav-item sidebar-help-compact" title="Besoin d’un coup de main ?" aria-label="Besoin d’un coup de main ? Ouvrir les réclamations" onclick="navigate('tickets')">${icon('help')}</button>`);
    lastY = window.scrollY; mode = 'top'; pinTop = 0; margin = 0; apply(0, 0);
    side.addEventListener('focusin', onFocus);
    observer = new ResizeObserver(() => update(true));
    observer.observe(side);
  }

  /* Le squelette est régénéré à chaque connexion / changement de rôle : on se raccroche juste après lui. */
  const stickyBaseShell = shell;
  shell = function () { const out = stickyBaseShell.apply(this, arguments); mount(); return out; };
  addEventListener('scroll', () => update(false), { passive: true });
  addEventListener('resize', () => update(true));
  addEventListener('keydown', onKey, { passive: true });
  if (root()) new MutationObserver(() => { if (side && !side.isConnected) unmount(); }).observe(root(), { childList: true });
  if (root()?.querySelector(':scope > .sidebar')) mount();
  window.stickySidebarState = () => ({ mode, pinTop, margin });   // lecture seule, utile aux parcours QA
})();
