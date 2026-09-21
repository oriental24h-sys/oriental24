const $ = (s) => document.querySelector(s);
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const paths = {
  grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  box: "M21 8l-9 5-9-5 M12 13v9 M3 7l9-5 9 5v10l-9 5-9-5z M7.5 4.5l9 5",
  truck:
    "M1 5h13v12H1z M14 9h4l4 5v3h-8 M5 17a2 2 0 1 0 0 4 2 2 0 0 0 0-4 M18 17a2 2 0 1 0 0 4 2 2 0 0 0 0-4",
  wallet: "M3 6h16v14H3z M3 6V3h14v3 M15 11h6v5h-6z M17 13.5h1",
  users:
    "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M17 4a4 4 0 0 1 0 8 M22 21v-2a4 4 0 0 0-3-4",
  user: "M20 21v-2a7 7 0 0 0-14 0v2 M13 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8",
  chart: "M4 3v18h17 M8 15v3 M13 10v8 M18 5v13",
  settings:
    "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M10 2h4l1 3 3 1 3 2-1 4 1 4-3 2-3 1-1 3h-4l-1-3-3-1-3-2 1-4-1-4 3-2 3-1z",
  ticket:
    "M3 5h18v5a2 2 0 0 0 0 4v5H3v-5a2 2 0 0 0 0-4z M15 5v3 M15 11v2 M15 16v3",
  print: "M6 9V2h12v7 M6 18H3V9h18v9h-3 M6 14h12v8H6z M17 11h1",
  pin: "M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0 M12 7a3 3 0 1 0 0 6 3 3 0 0 0 0-6",
  search: "M10.5 3a7.5 7.5 0 1 0 0 15 7.5 7.5 0 0 0 0-15 M16 16l5 5",
  bell: "M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9 M10 21h4",
  chevron: "M9 5l7 7-7 7",
  down: "M6 9l6 6 6-6",
  plus: "M12 5v14 M5 12h14",
  arrow: "M4 12h16 M14 6l6 6-6 6",
  back: "M20 12H4 M10 6l-6 6 6 6",
  upload: "M12 17V3 M7 8l5-5 5 5 M4 16v5h16v-5",
  download: "M12 3v12 M7 10l5 5 5-5 M4 16v5h16v-5",
  calendar: "M4 5h16v16H4z M16 2v6 M8 2v6 M4 10h16",
  check: "M5 12l4 4L19 6",
  checkcircle: "M22 11v1a10 10 0 1 1-6-9 M22 3L12 13l-3-3",
  clock: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20 M12 6v6l4 2",
  logout: "M9 3H3v18h6 M10 12h12 M18 8l4 4-4 4",
  help: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20 M9 9a3 3 0 1 1 5 2c-2 1-2 2-2 3 M12 17h.01",
  globe:
    "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20 M2 12h20 M12 2c6 6 6 14 0 20-6-6-6-14 0-20",
  edit: "M16 3l5 5-12 12-6 1 1-6z M14 5l5 5",
  close: "M6 6l12 12 M6 18L18 6",
  refresh: "M20 7a9 9 0 1 0 1 10 M20 2v6h-6",
  shield: "M12 2l9 4v6c0 5-9 10-9 10S3 17 3 12V6z M8 12l3 3 5-6",
  layers: "M12 2l10 5-10 5L2 7z M2 12l10 5 10-5 M2 17l10 5 10-5",
  up: "M5 16l5-5 4 3 7-9 M15 5h6v6",
  menu: "M3 6h18 M3 12h18 M3 18h18",
  mail: "M3 5h18v14H3z M3 5l9 7 9-7",
  phone: "M7 3H3c-1 10 8 19 18 18v-4l-5-2-2 3-8-8 3-2z",
  file: "M14 2H4v20h16V8z M14 2v6h6 M8 12h8 M8 16h6",
  return: "M4 8h11a6 6 0 0 1 0 12h-3 M9 3L4 8l5 5",
  link: "M10 13a5 5 0 0 0 7 0l4-4a5 5 0 0 0-7-7l-2 2 M14 11a5 5 0 0 0-7 0l-4 4a5 5 0 0 0 7 7l2-2",
  lock: "M5 10h14v12H5z M8 10V6a4 4 0 0 1 8 0v4",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12 M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6",
};
function icon(n, cls = "") {
  return `<svg class="ico ${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[n] || paths.box}"/></svg>`;
}
const money = (v) =>
  Number(v || 0).toLocaleString("fr-MA", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
const int = (v) => Number(v || 0).toLocaleString("fr-FR");
const date = (v) =>
  v
    ? new Date(v).toLocaleDateString("fr-FR", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      })
    : "—";
const initials = (n) =>
  (n || "")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((x) => esc(x[0]))
    .join("")
    .toUpperCase();
const roleName = (r) =>
  ({
    admin: "Administrateur",
    client: "Espace client",
    livreur: "Espace livreur",
    agent: "Agent réception",
  })[r] || r;
function tag(s) {
  const cls = [
    "Livré",
    "Réglée",
    "Résolu",
    "Réceptionnée",
    "Acceptée",
    "Ramassé",
  ].includes(s)
    ? "good"
    : ["En livraison", "Au hub", "En cours", "Planifié", "En transit", "Transit", "Réceptionné", "Reçu par le livreur", "Intéressé"].includes(
          s,
        )
      ? "blue"
      : ["Retourné", "Refusé", "Refusée", "Annulé"].includes(s)
        ? "bad"
        : ["Programmé", "Reporté", "À régler", "En attente", "Demandé"].includes(s)
          ? "warn"
          : "";
  return `<span class="tag ${cls}">${esc(s)}</span>`;
}
let modalCleanup = null;
let S = null,
  view = "dashboard",
  settingsTab = "cities",
  listPage = 1,
  filters = { q: "", status: "", city: "", from: "", to: "" },
  publicCities = [];
async function api(url, method = "GET", data, background = false) {
  const r = await fetch("/api" + url, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(background ? {"X-Background-Poll":"1"} : {}),
      ...(S?.csrf ? { "X-CSRF-Token": S.csrf } : {}),
    },
    ...(data !== undefined ? { body: JSON.stringify(data) } : {}),
  });
  let d;
  try {
    d = await r.json();
  } catch {
    throw Error("Le serveur ne répond pas. Réessayez.");
  }
  if (r.status === 401 && url !== "/login" && S && typeof securityExpired === "function") securityExpired();
  if (!r.ok) throw Error(d.error || "Une erreur est survenue.");
  return d;
}
/* v1.4.17 · audit pilotage : un conflit de version (409) dans un dialogue ne doit
   plus être subi comme une erreur « aléatoire ». On relit la fiche, on remonte la
   version à jour, puis on renvoie UNE FOIS l’intention déclarée par l’utilisateur.
   Si le conflit persiste après cette relecture, l’erreur originale est affichée :
   le verrou optimiste garde son rôle de garde-fou. */
const CONFLICT_RX = /modifi|chang|actualisez|rechargez|rouvrez|recréez|version invalide/i;
async function api409(send, fetchFresh) {
  try { return await send(undefined); }
  catch (e) {
    if (!CONFLICT_RX.test(String((e && e.message) || "")) || typeof fetchFresh !== "function") throw e;
    let fresh;
    try { fresh = await fetchFresh(); } catch { throw e; }
    if (!fresh || typeof fresh !== "object" || !Object.keys(fresh).length) throw e;
    const res = await send(fresh);
    toast("La fiche venait d’être modifiée par ailleurs : données actualisées, enregistrement repris.");
    return res;
  }
}
function toast(msg, error = false) {
  $("#toast-root").innerHTML =
    `<div class="toast ${error ? "error" : ""}" role="status">${icon(error ? "help" : "checkcircle")}${esc(msg)}</div>`;
  clearTimeout(window.toastTimer);
  window.toastTimer = setTimeout(() => ($("#toast-root").innerHTML = ""), 4500);
}
function empty(
  title = "Aucune donnée pour le moment",
  msg = "Vos données apparaîtront ici.",
  action = "",
) {
  return `<div class="empty">${icon("box")}<h3>${esc(title)}</h3><p>${esc(msg)}</p>${action}</div>`;
}
function closeModal() {
  if (modalCleanup) {
    const cleanup = modalCleanup;
    modalCleanup = null;
    cleanup();
  }
  $("#modal-root").innerHTML = "";
  document.body.style.overflow = "";
}
function modal(title, body, wide = false) {
  if (modalCleanup) {
    const cleanup = modalCleanup;
    modalCleanup = null;
    cleanup();
  }
  $("#modal-root").innerHTML =
    `<div class="modal-backdrop" onclick="if(event.target===this)closeModal()"><section class="modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="modal-header"><h2>${esc(title)}</h2><button class="icon-btn" onclick="closeModal()" aria-label="Fermer">${icon("close")}</button></div><div class="modal-body">${body}</div></section></div>`;
  document.body.style.overflow = "hidden";
  // Focus synchronously: a delayed timer could steal focus from the next field/modal.
  const dialog = $("#modal-root .modal");
  (dialog.querySelector('input:not([type="hidden"]),select,textarea') || dialog.querySelector('button'))?.focus({preventScroll:true});
}
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeModal();
    $(".sidebar")?.classList.remove("open");
  }
  if ((e.ctrlKey || e.metaKey) && e.key === "k" && S) {
    e.preventDefault();
    navigate("parcels").then(() => $("#parcel-search")?.focus());
  }
  if (e.key === "Tab" && $(".modal")) {
    const nodes = [
      ...$(".modal").querySelectorAll("button,input,select,textarea,a"),
    ].filter((n) => !n.disabled);
    if (!nodes.length) return;
    if (e.shiftKey && document.activeElement === nodes[0]) {
      e.preventDefault();
      nodes.at(-1).focus();
    } else if (!e.shiftKey && document.activeElement === nodes.at(-1)) {
      e.preventDefault();
      nodes[0].focus();
    }
  }
});
function input(
  name,
  label,
  value = "",
  type = "text",
  required = true,
  extra = "",
) {
  return `<div class="field"><label for="f-${name}">${label}${required ? " *" : ""}</label><input id="f-${name}" name="${name}" type="${type}" value="${esc(value)}" ${required ? "required" : ""} ${extra}></div>`;
}
function select(name, label, options, value = "", required = true) {
  return `<div class="field"><label for="f-${name}">${label}${required ? " *" : ""}</label><select id="f-${name}" name="${name}" ${required ? "required" : ""}>${options.map(([v, t]) => `<option value="${esc(v)}" ${String(v) === String(value) ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></div>`;
}
function textarea(name, label, value = "", required = false) {
  return `<div class="field full"><label for="f-${name}">${label}${required ? " *" : ""}</label><textarea id="f-${name}" name="${name}" ${required ? "required" : ""}>${esc(value)}</textarea></div>`;
}
function form(body, label = "Enregistrer") {
  return `<form id="modal-form"><div class="form-error" role="alert"></div><div class="form-grid">${body}</div><div class="form-actions"><button type="button" class="btn" onclick="closeModal()">Annuler</button><button class="btn primary" type="submit">${icon("check")}${label}</button></div></form>`;
}
function bindForm(handler, id = "modal-form") {
  const f = document.getElementById(id);
  f.onsubmit = async (e) => {
    e.preventDefault();
    const b = f.querySelector("[type=submit]");
    b.disabled = true;
    const err = f.querySelector(".form-error");
    if (err) err.style.display = "none";
    try {
      const d = Object.fromEntries(new FormData(f));
      for (const x of f.querySelectorAll("[type=checkbox]"))
        d[x.name] = x.checked;
      await handler(d);
    } catch (e) {
      if (err) {
        err.textContent = e.message;
        err.style.display = "block";
      } else toast(e.message, true);
    } finally {
      b.disabled = false;
    }
  };
}
async function refresh() {
  S = await api("/bootstrap");
}
async function saved(msg = "Modifications enregistrées") {
  await refresh();
  await renderView();
  closeModal();
  toast(msg);
}
function routeArt() {
  return `<svg class="route-art" viewBox="0 0 200 100" fill="none"><path d="M9 82C47 82 24 20 65 20s12 61 55 61 30-60 62-60" stroke="#eab990" stroke-width="2" stroke-dasharray="5 5"/><circle cx="10" cy="82" r="7" fill="#fff9f1" stroke="#f2c19a" stroke-width="2"/><path d="M168 14a14 14 0 0 1 28 0c0 13-14 25-14 25s-14-12-14-25" fill="#fc9140"/><circle cx="182" cy="14" r="4" fill="#fff"/><g transform="translate(61 37) rotate(-9)"><rect width="58" height="38" rx="6" fill="#fffaf5" stroke="#edc5a5"/><path d="M58 13h15l13 14v11H58" fill="#ffb980"/><circle cx="15" cy="40" r="7" fill="#b97d50"/><circle cx="69" cy="40" r="7" fill="#b97d50"/><path d="M63 17h8l8 9H63" fill="#fff9f2"/><path d="M13 15h30M13 22h21" stroke="#ff9d51" stroke-width="3" stroke-linecap="round"/></g></svg>`;
}

async function renderPublic() {
  S = null;
  document.title = "ORIENTAL24 — La livraison, plus proche de vous.";
  try {
    publicCities = (await api("/public")).cities;
  } catch {
    publicCities = [];
  }
  $("#root").innerHTML =
    `<div class="public"><nav class="public-nav"><a href="/" aria-label="ORIENTAL24 accueil"><img class="wordmark" src="/static/wordmark.png" alt="ORIENTAL24"></a><div class="public-links"><a href="#services">Nos services</a><a href="#couverture">Villes & tarifs</a><a href="#faq">Questions fréquentes</a></div><div class="flex"><a class="btn" href="/login">Espace client ${icon("arrow")}</a><button class="btn primary public-register" onclick="renderLogin(true)">Devenir partenaire</button></div></nav><section class="public-hero"><div><span class="public-badge"><span class="dot"></span>VOTRE PARTENAIRE DANS L’ORIENTAL</span><h1>Vos colis.<br>Notre région.<br><em>Une vraie proximité.</em></h1><p>De votre boutique à la porte de vos clients, ORIENTAL24 vous accompagne dans vos livraisons à domicile. Simple, local et toujours à vos côtés.</p><div class="hero-actions"><button class="btn primary" onclick="renderLogin(true)">Commencer à expédier ${icon("arrow")}</button><a href="#couverture" class="btn">Découvrir nos villes</a></div><div class="hero-trust"><span>${icon("checkcircle")}Suivi de vos colis</span><span>${icon("checkcircle")}Paiement à la livraison</span></div></div><div class="hero-visual"><div class="hero-orbit"></div><img src="/static/van.png" alt="Véhicule de livraison ORIENTAL24"><div class="float-card top"><span class="stat-icon green">${icon("checkcircle")}</span><div><b>Livraison de proximité</b><small>Au cœur de l’Oriental</small></div></div><div class="float-card bottom"><span class="stat-icon">${icon("pin")}</span><div><b>Un réseau qui grandit</b><small>Consultez notre couverture actuelle</small></div></div></div></section><div class="public-strip"><div>${icon("truck")}<div><b>Ramassage & livraison</b><small>Un partenaire pour chaque étape</small></div></div><div>${icon("wallet")}<div><b>Paiement à la livraison</b><small>Vos encaissements, en toute clarté</small></div></div><div>${icon("shield")}<div><b>Un espace qui vous simplifie la vie</b><small>Colis, suivi et factures au même endroit</small></div></div></div><section class="public-section" id="services"><div class="section-heading"><div class="eyebrow">De votre boutique à leur porte</div><h2>La logistique, en plus simple.</h2><p>Vous développez votre activité. Nous rapprochons vos clients.</p></div><div class="service-grid">${[
      [
        "box",
        "Expédiez en quelques clics",
        "Ajoutez vos colis dans votre espace, choisissez une ville desservie et préparez votre ramassage.",
      ],
      [
        "pin",
        "Gardez le fil de vos livraisons",
        "Retrouvez les étapes de chaque colis et les mises à jour de votre livreur dans un historique clair.",
      ],
      [
        "wallet",
        "Pilotez vos encaissements",
        "Consultez les montants collectés, les frais et les règlements depuis votre espace client.",
      ],
    ]
      .map(
        ([i, t, p]) =>
          `<article class="service-card"><div class="stat-icon">${icon(i)}</div><h3>${t}</h3><p>${p}</p></article>`,
      )
      .join(
        "",
      )}</div></section><div class="coverage" id="couverture"><section class="public-section coverage-inner"><div><div class="eyebrow orange">Ancrés dans l’Oriental</div><h2>Proches de vous.<br>Et de vos clients.</h2><p>Notre couverture évolue avec votre activité. Retrouvez ici les villes actuellement ouvertes à la livraison.</p><div class="city-pills">${publicCities.map((c) => `<span class="city-pill">${icon("pin")}${esc(c.name)}</span>`).join("") || "Aucune ville ouverte pour le moment."}</div></div><div class="tariff-box"><h3>Votre prochaine destination ?</h3><p>Consultez le tarif configuré pour votre ville.</p><label for="public-city">Ville de livraison</label><select id="public-city" onchange="updateTariff()">${publicCities.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}</select><div class="tariff-price" id="tariff-price"></div><div class="form-hint">Version de démonstration : villes et tarifs initiaux à valider par ORIENTAL24 avant ouverture commerciale.</div></div></section></div><section class="public-section" id="faq"><div class="section-heading"><div class="eyebrow">On vous répond</div><h2>Tout simplement.</h2></div><div class="faq-list"><details><summary>Dans quelles villes livrez-vous ?</summary><p>ORIENTAL24 se développe d’abord dans la région de l’Oriental. La liste ci-dessus est mise à jour depuis notre espace d’administration et indique les villes ouvertes à la livraison.</p></details><details><summary>Comment demander un ramassage ?</summary><p>Créez votre compte, ajoutez vos colis puis ouvrez la rubrique Ramassages. Choisissez une ville proposant le ramassage, une date et votre adresse.</p></details><details><summary>Comment fonctionne le paiement à la livraison ?</summary><p>Vous indiquez le montant à collecter. Une fois le colis livré, l’administration établit un relevé comprenant les montants encaissés et les frais. Le règlement est suivi dans votre rubrique Facturation.</p></details><details><summary>Comment suivre un colis ou contacter l’équipe ?</summary><p>Dans votre espace, ouvrez un colis pour consulter son historique. La rubrique Réclamations vous permet d’échanger avec l’administration sur votre demande.</p></details></div></section><footer class="public-footer"><div><div class="brandbox"><img class="wordmark" src="/static/wordmark.png" alt="ORIENTAL24"></div><p>Livraison à domicile. La proximité fait la différence.</p></div><a href="/login">Accéder à mon espace ${icon("arrow")}</a><span>© ${new Date().getFullYear()} ORIENTAL24</span></footer></div>`;
  updateTariff();
}
function updateTariff() {
  const c = publicCities.find((c) => String(c.id) === $("#public-city")?.value);
  if ($("#tariff-price"))
    $("#tariff-price").innerHTML = c
      ? `Livraison à ${esc(c.name)}<b>${money(c.fee)} <small>MAD / colis</small></b><small>Frais de retour : ${money(c.return_fee)} MAD · Ramassage ${c.pickup ? "disponible" : "non disponible"}</small>`
      : "Aucun tarif disponible.";
}
function renderLogin(register = false) {
  if (!RUNTIME.registration) register = false;
  history.replaceState(null, "", "/login");
  document.title = "Connexion — ORIENTAL24";
  $("#root").innerHTML =
    `<div class="login-page"><aside class="login-brand-panel"><a href="/" class="brandbox"><img class="wordmark" src="/static/wordmark.png" alt="ORIENTAL24"></a><div><div class="eyebrow" style="color:#e89a61">La proximité fait la différence</div><h1>Votre activité avance.<br><span>Nous livrons la suite.</span></h1><p>Un espace unique pour vos colis, vos équipes et vos encaissements. Bienvenue chez vous.</p><div class="login-illustration"><img src="/static/van.png" alt="Livraison ORIENTAL24"></div></div><small>ORIENTAL24 · Livraison à domicile · ${new Date().getFullYear()}</small></aside><main class="login-form-side"><div class="login-form"><a href="/" class="back-link">${icon("back")}Retour au site</a><div class="eyebrow">Votre espace ORIENTAL24</div><h2>${register ? "Bienvenue dans le réseau." : "Heureux de vous retrouver."}</h2><p>${register ? "Créez votre compte client et préparez vos premières expéditions." : "Connectez-vous pour suivre votre activité."}</p><form id="login-form"><div class="form-error" role="alert"></div>${register ? input("name", "Nom complet") + select("client_type", "Type de client", clientTypeOptions) + input("company", "Boutique / Société") + input("phone", "Téléphone", "", "tel") : ""}${input("email", "Adresse e-mail", "", "email", true, 'autocomplete="username"')}${input("password", "Mot de passe", "", "password", true, `minlength="${register ? 10 : 1}" autocomplete="${register ? "new-password" : "current-password"}"`)}<button class="btn primary" type="submit">${register ? "Créer mon compte" : "Se connecter"} ${icon("arrow")}</button></form><div class="login-register">${register ? "Déjà partenaire ?" : "Pas encore de compte ?"} <a onclick="RUNTIME.registration?renderLogin(${!register}):toast('Inscription publique fermée. Contactez l’administration.',true)">${register ? "Se connecter" : "Devenir client"}</a></div>${!register && RUNTIME.demo ? `<div class="demo-accounts"><p>EXPLORER LA VERSION DE DÉMONSTRATION</p><div class="demo-buttons"><button class="btn" onclick="demoLogin('admin')">${icon("shield")}Admin</button><button class="btn" onclick="demoLogin('client')">${icon("box")}Client</button><button class="btn" onclick="demoLogin('livreur')">${icon("truck")}Livreur</button><button class="btn" onclick="demoLogin('agent')">${icon("bell")}Agent réception</button></div></div>` : ""}<div class="login-note">${RUNTIME.demo?"Données fictives · Ne saisissez pas de données sensibles dans cette démo.":RUNTIME.registration?"Compte client · Vérification d’e-mail non activée.":"Inscription publique fermée. Demandez votre compte à l’administration."}</div></div></main></div>`;
  bindForm(async (d) => {
    await api(register ? "/register" : "/login", "POST", d);
    await enterApp();
  }, "login-form");
}
async function demoLogin(role) {
  try {
    await api("/login", "POST", {
      email: role + "@oriental24.ma",
      password: "Oriental24!Demo",
    });
    await enterApp();
  } catch (e) {
    toast(e.message, true);
  }
}
async function enterApp() {
  await refresh();
  history.replaceState(null, "", "/app");
  view = S?.user?.role === "agent" ? "partner-palettes" : "dashboard";
  shell();
  await renderView();
}
const menu = [
  [
    "VUE D’ENSEMBLE",
    [
      ["dashboard", "grid", "Tableau de bord"],
      ["analytics", "chart", "Statistiques", ["admin"]],
    ],
  ],
  [
    "EXPÉDITIONS",
    [
      ["parcels", "box", "Colis"],
      ["pickups", "truck", "Ramassages", ["admin", "client"]],
      ["pallets", "layers", "Palettes", ["admin"]],
      ["stock", "layers", "Stock & produits", ["admin", "client"]],
      ["print", "print", "Impression"],
    ],
  ],
  [
    "GESTION",
    [
      ["invoices", "wallet", "Facturation", ["admin", "client", "livreur"]],
      ["driver-finance", "wallet", "Caisse livreurs", ["admin", "livreur"]],
      ["drivers", "users", "Livreurs", ["admin"]],
      ["clients", "user", "Clients", ["admin"]],
      ["requests", "return", "Demandes"],
      ["tickets", "ticket", "Réclamations"],
    ],
  ],
  [
    "ESPACE PERSONNEL",
    [
      ["settings", "settings", "Paramètres", ["admin"]],
      ["profile", "user", "Mon profil"],
    ],
  ],
];
const titles = {
  dashboard: "Tableau de bord",
  parcels: "Gestion des colis",
  pickups: "Ramassages",
  pallets: "Palettes",
  stock: "Stock & produits",
  print: "Centre d’impression",
  invoices: "Facturation",
  drivers: "Livreurs",
  clients: "Clients",
  requests: "Demandes de modification",
  tickets: "Réclamations",
  settings: "Paramètres",
  profile: "Mon profil",
  analytics: "Statistiques & performance",
  "driver-finance": "Caisse & commissions livreurs",
};
function shell() {
  const u = S.user;
  $("#root").innerHTML =
    `<aside class="sidebar"><a class="brand" href="/"><span class="brandbox"><img class="wordmark" src="/static/wordmark.png" alt="ORIENTAL24"></span></a><div class="workspace-label">${roleName(u.role).toUpperCase()}</div><nav class="nav-scroll">${menu
      .map(([section, items]) => {
        const vis = items.filter((x) => (!x[3] || x[3].includes(u.role)) && (x[0]!=='partner-palettes'||ppAccess(u)) && (u.role!=='agent'||['partner-palettes','alerts','tickets','notifications','announcements','profile','security'].includes(x[0])));
        return vis.length
          ? `<div class="nav-section">${section}</div>${vis.map(([key, i, t]) => `<button class="nav-item ${key === view ? "active" : ""}" data-nav="${key}" onclick="navigate('${key}')">${icon(i)}<span>${t}</span>${key === "parcels" ? `<span class="nav-count">${S.parcels.length}</span>` : ""}</button>`).join("")}`
          : "";
      })
      .join(
        "",
      )}</nav><div class="sidebar-bottom"><div class="sidebar-help"><div class="flex">${icon("help")}<b>Besoin d’un coup de main ?</b></div>Notre équipe vous accompagne.<button onclick="navigate('tickets')">Ouvrir les réclamations →</button></div><div class="sidebar-foot"><span>ORIENTAL24 · v1.4.16</span><span>${RUNTIME.demo?"VERSION DÉMO":"MODE SANS DÉMO"}</span></div></div></aside><div class="layout"><header class="topbar"><div class="flex"><button class="icon-btn mobile-menu" onclick="$('.sidebar').classList.toggle('open')" aria-label="Ouvrir le menu">${icon("menu")}</button><div class="breadcrumb">Espace ${u.role === "admin" ? "administrateur" : u.role}${icon("chevron")}<strong id="breadcrumb-title">${titles[view]}</strong></div></div><div class="top-actions"><button class="global-search" onclick="navigate('parcels').then(()=>$('#parcel-search')?.focus())">${icon("search")}Rechercher un colis… <kbd>⌘ K</kbd></button><span class="flex lang" style="font-size:10px;gap:5px">${icon("globe")}FR</span><button class="icon-btn notification" onclick="opsOffline?showAnnouncement():navigate('notifications')" aria-label="Notifications">${icon("bell")}</button><button class="top-profile" onclick="navigate('profile')"><span class="avatar orange">${initials(u.name)}</span><span class="profile-text"><b>${esc(u.name)}</b><small>${roleName(u.role)}</small></span>${icon("down")}</button></div></header><main class="content" id="content"></main></div>`;
}
async function navigate(v) {
  if (!S) return;
  // Agent de réception : espace limité à ses tâches, aucun contournement via l’URL.
  if (S.user.role==='agent'&&!['partner-palettes','alerts','tickets','profile','notifications','announcements','security'].includes(v)) v='partner-palettes';
  if (S.user.role === "livreur" && ["parcels","dashboard","print"].includes(v)) { try { const owner=S.user.id,fresh=await api("/bootstrap"); if(S?.user?.id!==owner||fresh.user.id!==owner)return; S=fresh; } catch(e) {toast(e.message,true);return;} }
  view = v;
  listPage = 1;
  closeWorkspaceMenu();
  document
    .querySelectorAll("[data-nav]")
    .forEach((x) => x.classList.toggle("active", x.dataset.nav === v));
  $("#breadcrumb-title").textContent = titles[v] || v;
  await renderView();
  window.scrollTo({ top: 0, behavior: "instant" });
}
function heading(title, sub, actions = "") {
  return `<div class="page-heading"><div><h1>${title}</h1><p>${sub}</p></div><div class="heading-actions">${actions}</div></div>`;
}
function footer() {
  return `<footer class="footer"><span>© ${new Date().getFullYear()} ORIENTAL24. Tous droits réservés.</span><span><i class="status-dot"></i>${RUNTIME.demo?"Version de démonstration · Données fictives":"Session sécurisée côté serveur · ORIENTAL24"}</span></footer>`;
}
async function renderView(background = false) {
  document.title = (titles[view] || "Mon espace") + " — ORIENTAL24";
  const current = view, owner = S?.user?.id;
  try {
    let html = "";
    switch (view) {
      case "dashboard":
        html = dashboard();
        break;
      case "parcels":
        html = parcelsView();
        break;
      case "announcements":
        html = announcementsView(await api("/announcements/manage"));
        break;
      case "settings":
        html = settingsView();
        break;
      case "profile":
        html = profileView();
        break;
      case "drivers":
        html = driverWorkspaceView(await api("/drivers-workspace"));
        break;
      case "clients":
        html = usersView();
        break;
      case "analytics":
        html = analyticsView();
        break;
      case "print":
        html = printView();
        break;
      case "tickets":
        html = ticketsView(await api("/tickets"));
        break;
      case "pickups":
        html = pickupsView(await api("/pickups"));
        break;
      case "partner-palettes":
        html = partnerPalettesView(await api("/partner-palettes?"+ppQuery()));
        break;
      case "alerts":
        html = alertsView(await api("/alerts"));
        break;
      case "pallets":
        html = palletsView(await api("/pallets"));
        break;
      case "support-team":
        html = supportTeamView(await api("/support-contacts"));
        break;
      case "security":
        html = securityView(await api('/security/sessions'),S.user.role==='admin'?await api('/security/deployment'):null);
        break;
      case "account-dossiers":
        html = accountsView(await api('/account-dossiers'));
        break;
      case "stock-analytics":
        html = stockAnalyticsView(await api('/fulfillment/analytics?'+new URLSearchParams(stockPeriod)));
        break;
      case "fulfillment":
        html = fulfillmentView(await api('/fulfillment/orders'));
        break;
      case "documents":
        html = opsDocsView(await api('/logistics/documents'));
        break;
      case "ops-settings":
        html = opsSettingsView(await api('/logistics/config'));
        break;
      case "notifications":
        html = opsNotificationsView(await api('/logistics/notifications'));
        break;
      case "ops-analytics":
        html = opsAnalyticsView(await api('/logistics/analytics?'+new URLSearchParams(opsPeriod)));
        break;
      case "driver-finance":
        html = driverFinanceView(
          ...(await Promise.all([
            api("/driver-finance"),
            api("/driver-finance/terms"),
          ])),
        );
        break;
      case "invoices": {
        const data=await api("/billing?"+billingQuery(),"GET",undefined,background);
        if(current!==view||S?.user?.id!==owner)return;
        html=billingView(data);break;
      }
      case "stock":
        html = stockView(
          ...(await Promise.all([
            api("/products"),
            api("/stock/requests"),
            api("/stock/movements"),
          ])),
        );
        break;
      case "requests":
        html = requestsView(await api("/requests"));
        break;
    }
    const notices = current === "print" ? [] : await api("/announcements","GET",undefined,background);
    if (current !== view || S?.user?.id !== owner || !$("#content")) return;
    $("#content").innerHTML = (current === "print" ? "" : announcementMarkup(notices)) + html + footer();
    if (view === "parcels") drawParcelTable();
    if (view === "drivers") drawDriverWorkspace();
    if (view === "profile") bindProfile();
    if (view === "settings" && settingsTab === "general") bindSettings();
  } catch (e) {
    if (background || !$("#content") || current !== view || S?.user?.id !== owner) return;
    $("#content").innerHTML =
      empty(
        "Impossible de charger la page",
        e.message,
        `<button class="btn" onclick="renderView()">Réessayer</button>`,
      ) + footer();
  }
}
function showAnnouncement() {
  modal(
    "Actualités ORIENTAL24",
    `<div class="form-hint orange">${esc(S.settings.announcement || "Aucune annonce pour le moment.")}</div><p class="muted" style="font-size:12px;margin-top:20px">Les annonces sont configurables depuis les paramètres de l’administration.</p>`,
  );
}
function stat(label, value, unit, i, color, foot) {
  return `<div class="stat"><div class="stat-top">${label}<span class="stat-icon ${color}">${icon(i)}</span></div><div class="stat-value">${value}${unit ? `<small>${unit}</small>` : ""}</div><div class="stat-foot">${foot}</div></div>`;
}
function lineChart() {
  const ds = Array.from({ length: 7 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - 6 + i);
    const key = [
      d.getFullYear(),
      String(d.getMonth() + 1).padStart(2, "0"),
      String(d.getDate()).padStart(2, "0"),
    ].join("-");
    return {
      label: d.toLocaleDateString("fr-FR", { weekday: "short" }),
      all: S.parcels.filter((p) => p.created_at.startsWith(key)).length,
      del: S.parcels.filter(
        (p) => p.created_at.startsWith(key) && p.status === "Livré",
      ).length,
    };
  });
  const max = Math.ceil(Math.max(4, ...ds.map((d) => d.all)) / 4) * 4;
  const points = (key) =>
    ds.map((d, i) => `${43 + i * 83},${174 - (d[key] / max) * 143}`).join(" ");
  return `<svg class="chart" viewBox="0 0 565 215" role="img" aria-label="Colis créés et livrés par date de création sur les sept derniers jours"><defs><linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff8d3d" stop-opacity=".15"/><stop offset="1" stop-color="#ff8d3d" stop-opacity="0"/></linearGradient></defs>${[0, 1, 2, 3, 4].map((i) => `<line class="grid" x1="37" y1="${174 - i * 36}" x2="549" y2="${174 - i * 36}"/><text x="24" y="${178 - i * 36}" text-anchor="end">${Math.round((max * i) / 4)}</text>`).join("")}<polygon class="area" points="43,174 ${points("all")} 541,174"/><polyline class="line2" points="${points("del")}"/><polyline class="line" points="${points("all")}"/>${ds.map((d, i) => `<circle cx="${43 + i * 83}" cy="${174 - (d.all / max) * 143}" r="3" fill="white" stroke="#ff7618" stroke-width="2"><title>${d.label} : ${d.all} créés, ${d.del} livrés</title></circle><text x="${43 + i * 83}" y="204" text-anchor="middle">${d.label}</text>`).join("")}</svg>`;
}
function dashboard() {
  const ps = S.parcels,
    del = ps.filter((p) => p.status === "Livré"),
    active = ps.filter(
      (p) => !["Livré", "Retourné", "Refusé"].includes(p.status),
    ),
    cod = del.reduce((s, p) => s + p.amount, 0),
    rate = ps.length ? Math.round((del.length / ps.length) * 100) : 0;
  const cities = S.cities
    .map((c) => ({ ...c, count: ps.filter((p) => p.city_id === c.id).length }))
    .filter((c) => c.count)
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
  const isDriver = S.user.role === "livreur";
  return (
    heading(
      `Bonjour, ${esc(S.user.name.split(" ")[0])} <span style="font-size:22px">☀</span>`,
      isDriver
        ? "Votre tournée, vos colis et vos encaissements en un coup d’œil."
        : "Voici ce qui se passe chez ORIENTAL24 aujourd’hui.",
      `<span class="date-pill">${icon("calendar")}${new Date().toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })}</span>${!isDriver ? `<button class="btn primary" onclick="newParcel()">${icon("plus")}Nouveau colis</button>` : `<button class="btn primary" onclick="navigate('parcels')">${icon("truck")}Ma tournée</button>`}`,
    ) +
    `<section class="hero-banner"><div><div class="eyebrow">Votre partenaire de proximité</div><h2>L’Oriental, plus proche à chaque livraison.</h2><p>${esc(S.settings.announcement || "Suivez vos expéditions et accompagnez votre activité, au même endroit.")}</p></div>${routeArt()}</section><section class="stats">${stat("Total des colis", int(ps.length), "", "box", "", `${icon("box")}Dans votre périmètre`)}${stat("Colis en cours", int(active.length), "", "truck", "blue", `${icon("clock")}Colis non clôturés`)}${stat("Colis livrés", int(del.length), "", "checkcircle", "green", `<span class="green">${icon("up")} ${rate}%</span> du total des colis`)}${stat("Montant collecté", money(cod), "MAD", "wallet", "purple", `${icon("wallet")}COD des colis livrés`)}</section><section class="two-col"><article class="card"><div class="card-head"><div><h3>Activité des expéditions</h3><p>Par date de création · 7 derniers jours</p></div><div class="chart-legend"><span><i class="dot"></i>Créés</span><span><i class="dot navy"></i>Livrés</span></div></div><div class="chart-wrap">${lineChart()}</div></article><article class="card"><div class="card-head"><div><h3>Vos principales destinations</h3><p>Répartition des colis par ville</p></div>${icon("pin")}</div><div class="city-bars">${cities.map((c) => `<div class="city-row"><div class="flex between"><span>${esc(c.name)}</span><span class="muted">${c.count} colis <b style="color:#53667e;margin-left:10px;font-weight:500">${Math.round((c.count / ps.length) * 100)}%</b></span></div><div class="bar"><span style="width:${(c.count / Math.max(...cities.map((c) => c.count))) * 100}%"></span></div></div>`).join("") || empty("Pas encore de destination", "Ajoutez votre premier colis.")}</div></article></section><section class="card"><div class="card-head"><div><h3>${isDriver ? "Mes derniers colis" : "Derniers colis"}</h3><p>Les dernières expéditions de votre activité</p></div><button class="section-link" onclick="navigate('parcels')">Voir tous les colis ${icon("arrow")}</button></div>${parcelTable(ps.slice(0, 5), false)}<div class="table-footer"><span>${Math.min(ps.length, 5)} colis sur ${ps.length}</span><span>Mise à jour à l’ouverture de la page <button class="icon-btn" onclick="reloadView()" aria-label="Actualiser">${icon("refresh")}</button></span></div></section>`
  );
}
async function reloadView() {
  try {
    await refresh();
    await renderView();
    toast("Données actualisées");
  } catch (e) {
    toast(e.message, true);
  }
}
function parcelTable(rows, selectable = true) {
  if (!rows.length)
    return empty(
      "Aucun colis trouvé",
      "Essayez d’autres filtres ou ajoutez un nouveau colis.",
    );
  return `${S.user.role === "livreur" && view !== "print" ? driverCards(rows) : ""}<div class="table-wrap ${S.user.role === "livreur" && view !== "print" ? "driver-desktop-table" : ""}"><table><thead><tr>${selectable ? '<th style="width:30px"><input type="checkbox" style="width:13px" aria-label="Sélectionner tous" onchange="document.querySelectorAll(\'.parcel-select\').forEach(x=>x.checked=this.checked)"></th>' : ""}<th>Référence</th><th>Destinataire</th><th>Destination</th><th>Montant COD</th><th>Statut</th><th>${S.user.role === "client" ? "Livreur" : "Client / Boutique"}</th><th></th></tr></thead><tbody>${rows.map((p) => `<tr>${selectable ? `<td><input class="parcel-select" value="${p.id}" type="checkbox" style="width:13px" aria-label="Sélectionner ${esc(p.tracking)}"></td>` : ""}<td><button class="tracking" onclick="parcelDetail(${p.id})">${esc(p.tracking)}</button><span class="sub">${date(p.created_at)}</span></td><td><div class="recipient">${view==='print'?`<span class="avatar">${initials(p.recipient)}</span>`:parcelCopyButton(p)}<div><strong>${esc(p.recipient)}</strong><span class="sub">${esc(p.phone)}</span></div></div></td><td><span class="flex" style="gap:5px">${icon("pin")} ${esc(p.city)}</span></td><td><strong>${money(p.amount)}</strong> <span class="muted" style="font-size:9px">MAD</span>${p.invoice_id ? '<span class="sub green">Facturé</span>' : ""}</td><td>${view==='print'?tag(p.status):parcelStateControls(p)}</td><td>${esc(S.user.role === "client" ? p.driver || "Non affecté" : p.company || p.client)}</td><td><div class="parcel-row-actions">${view==='print'?'':parcelCityButton(p)+parcelClaimButton(p)}<button class="icon-btn" title="Ouvrir le colis" onclick="parcelDetail(${p.id})">${icon("chevron")}</button></div></td></tr>`).join("")}</tbody></table></div>`;
}
function parcelsView() {
  const create = S.user.role !== "livreur";
  return (
    heading(
      create ? "Gestion des colis" : "Mes colis",
      "Chaque colis a son histoire. Retrouvez-la ici.",
      `<a class="btn export-btn" href="/api/export">${icon("download")}Exporter CSV</a>${create ? `<button class="btn import-trigger" onclick="openImports()">${icon("upload")}Importer</button>` : ""}${create ? `<button class="btn primary" onclick="newParcel()">${icon("plus")}Nouveau colis</button>` : ""}`,
    ) +
    `<section class="card"><div class="tabs"><button class="active">${S.user.role === "livreur" ? "Mes colis assignés" : "Tous les colis"} <span class="tag" style="margin-left:6px">${S.parcels.length}</span></button><button onclick="filters.status='En livraison';$('#status-filter').value=filters.status;drawParcelTable()">En livraison</button><button onclick="filters.status='Livré';$('#status-filter').value=filters.status;drawParcelTable()">Livrés</button></div><div class="toolbar"><div class="search-field">${icon("search")}<input id="parcel-search" placeholder="Référence, nom, téléphone…" value="${esc(filters.q)}" oninput="filters.q=this.value;listPage=1;drawParcelTable()"></div><select id="status-filter" aria-label="Filtrer par statut" onchange="filters.status=this.value;listPage=1;drawParcelTable()"><option value="">Tous les statuts</option>${S.statuses.map((s) => `<option ${s === filters.status ? "selected" : ""}>${esc(s)}</option>`).join("")}</select><select aria-label="Filtrer par ville" onchange="filters.city=this.value;listPage=1;drawParcelTable()"><option value="">Toutes les villes</option>${S.cities.map((c) => `<option value="${c.id}" ${String(c.id) === filters.city ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select><div class="spacer"></div><button class="btn sm" onclick="openScanner()">${icon("scan")}Scanner</button><button class="btn sm" onclick="printSelected()">${icon("print")}Étiquettes</button><button class="icon-btn" onclick="filters={q:'',city:'',status:'',from:'',to:''};listPage=1;renderView()" title="Réinitialiser les filtres">${icon("refresh")}</button></div><div id="parcel-table"></div></section>`
  );
}
function drawParcelTable() {
  if (!$("#parcel-table")) return;
  const q = filters.q.toLowerCase();
  const rows = S.parcels.filter(
    (p) =>
      (!q ||
        [p.tracking, p.recipient, p.phone, p.company, p.city].some((x) =>
          String(x).toLowerCase().includes(q),
        )) &&
      (!filters.status || p.status === filters.status) &&
      (!filters.city || String(p.city_id) === filters.city),
  );
  const pages = Math.max(1, Math.ceil(rows.length / 10));
  listPage = Math.min(listPage, pages);
  $("#parcel-table").innerHTML =
    parcelTable(rows.slice((listPage - 1) * 10, listPage * 10)) +
    `<div class="table-footer"><span>${rows.length ? (listPage - 1) * 10 + 1 : 0}–${Math.min(rows.length, listPage * 10)} sur ${rows.length} colis</span><div class="pagination"><button onclick="listPage=Math.max(1,listPage-1);drawParcelTable()" aria-label="Page précédente">‹</button>${Array.from({ length: pages }, (_, i) => `<button class="${listPage === i + 1 ? "active" : ""}" onclick="listPage=${i + 1};drawParcelTable()">${i + 1}</button>`).join("")}<button onclick="listPage=Math.min(${pages},listPage+1);drawParcelTable()" aria-label="Page suivante">›</button></div></div>`;
}
function clientOptions() {
  return [
    ["", "Choisir un client"],
    ...S.users
      .filter((u) => u.role === "client" && u.active)
      .map((u) => [u.id, u.company || u.name]),
  ];
}
const clientTypeOptions = [['vendeur','Vendeur'],['societe_livraison','Société de livraison']];
function clientTypeLabel(u){return u?.client_type==='societe_livraison'?'Société de livraison':'Vendeur'}
function clientTrackingSlot(){return '<div class="full" id="client-tracking-slot"></div>'}
function bindClientTracking(){
 const node=$('#client-tracking-slot');if(!node)return;
 const update=()=>{if(!node.isConnected)return;const cl=S.user.role==='client'?S.user:S.users.find(u=>String(u.id)===$('#f-client_id')?.value);const company=cl?.client_type==='societe_livraison';node.innerHTML=company?`<div class="form-hint orange"><b>Société de livraison · votre tracking</b><br>Le code saisi sera conservé pour le suivi, les scans, les étiquettes et les factures. Aucun nouveau code ORIENTAL24 ne le remplace.</div>${input('tracking','Tracking de votre société','','text',true,'maxlength="80" autocomplete="off" spellcheck="false" placeholder="Ex. SOC-000123"')}<p class="sub">1 à 80 caractères : lettres, chiffres, . - _ / ; début par lettre ou chiffre. Les zéros initiaux et la casse sont conservés. Code unique sur la plateforme (sans distinction de casse).</p>`:`<div class="form-hint"><b>${cl?'Vendeur · tracking ORIENTAL24':'Choisissez un client'}</b><br>${cl?'Le code de suivi est généré automatiquement à la création du colis.':'Le mode de tracking dépend du type de client sélectionné.'}</div>`};
 $('#f-client_id')?.addEventListener('change',update);update();
}
function newParcel() {
  const cities = S.cities.filter((c) => c.delivery);
  modal(
    "Nouveau colis",
    form(
      `${S.user.role === "admin" ? select("client_id", "Client / Société", clientOptions()) : ""}${clientTrackingSlot()}${input("recipient", "Nom du destinataire")}${input("phone", "Téléphone", "", "tel", true, 'placeholder="06…"')}${select("city_id", "Ville de livraison", [["", "Choisir une ville"], ...cities.map((c) => [c.id, c.name + " — " + money(c.fee) + " MAD"])])}${input("amount", "Montant à collecter (MAD)", "", "number", true, 'min="0" max="1000000" step="0.01"')}${input("product", "Nature du produit", "", "text", false)}${textarea("address", "Adresse complète", "", true)}${textarea("note", "Note de livraison")}<div class="full form-hint">Seules les villes ouvertes à la livraison sont disponibles. Le tarif en vigueur est conservé sur le colis lors de sa création.</div>`,
      "Créer le colis",
    ),
  );
  bindClientTracking();
  bindForm(async (d) => {
    const r = await api("/parcels", "POST", d);
    await saved("Colis " + r.tracking + " créé");
  });
}
async function parcelDetail(id) {
  try {
    const d = await api("/parcels/" + id),
      p = { ...S.parcels.find((p) => p.id === id), ...d.parcel };
    modal(
      p.tracking,
      `<div class="detail-grid"><div><div class="detail-info"><div class="flex between"><h3>${esc(p.recipient)}</h3>${tag(p.status)}</div><p class="muted" style="font-size:12px">${esc(p.address)}<br>${esc(p.city)} · ${esc(p.phone)}</p><div class="detail-line"><span>À collecter</span><strong>${money(p.amount)} MAD</strong></div><div class="detail-line"><span>Frais de livraison</span><span>${money(p.fee)} MAD</span></div><div class="detail-line"><span>Produit</span><span>${esc(p.product || "—")}</span></div><div class="detail-line"><span>Livreur</span><span>${esc(p.driver || "Non affecté")}</span></div><div class="form-hint">${esc(p.note || "Aucune note pour ce colis.")}</div>${p.financial_locked ? `<div class="form-hint">${icon("lock")}Colis verrouillé dans un relevé livreur.</div>` : ""}</div><div class="flex" style="flex-wrap:wrap"><button class="btn sm" onclick="printLabels([${id}])">${icon("print")}Étiquette</button>${!opsOffline?`<button class="btn sm" onclick="openOpsParcel(${id})">${icon("clock")}Suivi opérationnel</button>`:""}${!p.invoice_id && !p.financial_locked && !p.operations_locked && S.user.role !== "client" ? `<button class="btn primary sm" onclick="changeStatus(${id})">${icon("edit")}Changer le statut</button>` : ""}${S.user.role === "admin" && !p.invoice_id && !p.financial_locked && !p.operations_locked ? `<button class="btn sm" onclick="assignDriver(${id})">${icon("user")}Affecter un livreur</button>` : ""}${!p.invoice_id && !p.financial_locked && !p.operations_locked && !["Livré", "Retourné", "Refusé"].includes(p.status) ? `<button class="btn sm" onclick="requestPrice(${id})">${icon("return")}Demande de prix</button>` : ""}</div></div><div><h3 style="font-size:14px">Chronologie d’activité</h3><div class="timeline">${d.events.map((e) => `<div class="timeline-item"><b>${esc(e.status)}</b><p>${esc(e.note)}</p><small>${esc(e.actor)} · ${date(e.created_at)} ${new Date(e.created_at).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}</small></div>`).join("")}</div></div></div>`,
      true,
    );
  } catch (e) {
    toast(e.message, true);
  }
}
function changeStatus(id) {
  const p = S.parcels.find((p) => p.id === id);
  const transitions = S.status_policy.driver_transitions;
  const options =
    S.user.role === "admin" ? S.statuses : transitions[p.status] || [];
  if (!options.length) {
    toast("Ce colis est clôturé. Contactez l’administration.", true);
    return;
  }
  modal(
    "Mettre à jour le colis",
    form(
      `<div class="full form-hint">${esc(p.tracking)} · État actuel : ${esc(p.status)}</div>${select(
        "status",
        "Nouveau statut",
        options.map((s) => [s, s]),
        p.status,
      )}${textarea("note", "Commentaire / motif")}<div class="full form-hint orange">Le statut « Livré » confirme que le montant de ${money(p.amount)} MAD a été collecté.</div>`,
    ),
  );
  bindForm(async (d) => {
    await api409(
      (f)=>api("/parcels/" + id, "PATCH", {...d,revision:f?f.ops_revision:(p.ops_revision||0)}),
      async()=>({ops_revision:(await api("/parcels/"+id)).parcel.ops_revision}),
    );
    await saved("Statut mis à jour");
    await parcelDetail(id);
  });
}
function assignDriver(id) {
  const p = S.parcels.find((p) => p.id === id);
  modal(
    "Affecter un livreur",
    form(
      select(
        "driver_id",
        "Livreur",
        [
          ["", "Sans affectation"],
          ...S.users
            .filter((u) => u.role === "livreur" && u.active)
            .map((u) => [u.id, u.name]),
        ],
        p.driver_id,
        false,
      ),
    ),
  );
  bindForm(async (d) => {
    await api("/parcels/" + id, "PATCH", d);
    await saved("Affectation enregistrée");
  });
}
function requestPrice(id) {
  const p = S.parcels.find((p) => p.id === id);
  modal(
    "Demande de changement de prix",
    form(
      `<div class="full form-hint">${esc(p.tracking)} · Prix actuel : ${money(p.amount)} MAD</div>${input("amount", "Nouveau montant (MAD)", p.amount, "number", true, 'min="0" step="0.01"')}${textarea("reason", "Motif de la demande", "", true)}`,
      "Envoyer la demande",
    ),
  );
  bindForm(async (d) => {
    await api("/requests", "POST", { ...d, parcel_id: id });
    await saved("Demande envoyée à l’administration");
  });
}
function settingsView() {
  return (
    heading(
      "Paramètres",
      "Votre réseau évolue. Vos réglages aussi.",
      `<button class="btn" onclick="editDriverInvoiceProfile()">${icon("file")}Coordonnées des factures</button><button class="btn" onclick="openDriverFinance('rates')">${icon("wallet")}Commissions livreurs</button>` +
        (settingsTab === "cities"
          ? `<button class="btn primary" onclick="cityForm()">${icon("plus")}Ajouter une ville</button>`
          : ""),
    ) +
    `<div class="card"><div class="tabs">${[
      ["cities", "Villes & couverture"],
      ["general", "Général"],
      ["integrations", "Intégrations"],
    ]
      .map(
        ([k, t]) =>
          `<button class="${settingsTab === k ? "active" : ""}" onclick="settingsTab='${k}';renderView()">${t}</button>`,
      )
      .join("")}</div>${
      settingsTab === "cities"
        ? `<div class="settings-intro"><div><h3>Une couverture sans limites techniques.</h3><p>Ajoutez des villes partout au Maroc, à votre rythme. Gérez séparément la livraison, le ramassage et les tarifs de chaque destination.</p></div><span class="tag good">${S.cities.filter((c) => c.delivery).length} villes ouvertes</span></div><div class="demo-notice" style="margin:18px 23px">Configuration initiale de démonstration. Validez les villes et les tarifs réellement desservis avant de les communiquer à vos clients.</div><div class="table-wrap"><table><thead><tr><th>Ville</th><th>Région</th><th>Livraison</th><th>Ramassage</th><th>Tarif livraison</th><th>Frais de retour</th><th></th></tr></thead><tbody>${S.cities.map((c) => `<tr><td><strong>${esc(c.name)}</strong></td><td>${esc(c.region)}</td><td><span class="switch"><input type="checkbox" ${c.delivery ? "checked" : ""} aria-label="Livraison à ${esc(c.name)}" onchange="toggleCity(${c.id},'delivery',this.checked)"><span>${c.delivery ? "Active" : "Inactive"}</span></span></td><td><span class="switch"><input type="checkbox" ${c.pickup ? "checked" : ""} aria-label="Ramassage à ${esc(c.name)}" onchange="toggleCity(${c.id},'pickup',this.checked)"><span>${c.pickup ? "Actif" : "Inactif"}</span></span></td><td><strong>${money(c.fee)}</strong> MAD</td><td>${money(c.return_fee)} MAD</td><td><button class="icon-btn" onclick="cityForm(${c.id})" aria-label="Modifier ${esc(c.name)}">${icon("edit")}</button></td></tr>`).join("")}</tbody></table></div><div class="table-footer"><span>${S.cities.length} villes configurées · Toutes régions confondues</span><span>Les colis existants conservent leur tarif.</span></div>`
        : settingsTab === "general"
          ? `<div class="settings-form"><div class="flex" style="margin-bottom:28px"><img src="/static/logo.png" alt="Logo ORIENTAL24" style="width:155px;border:1px solid var(--line);border-radius:8px;padding:10px"><div><h3>ORIENTAL24</h3><p class="muted" style="font-size:11px;margin-top:7px">Livraison à domicile · Bleu nuit & orange<br>Logo fourni par votre équipe</p></div></div><form id="settings-form"><div class="form-error"></div>${textarea("announcement", "Annonce affichée sur les tableaux de bord", S.settings.announcement || "")}<p class="form-hint" style="margin-top:14px">L’annonce est visible par les clients et les livreurs. Évitez d’y publier des informations confidentielles.</p><div style="border-top:1px solid var(--line);padding-top:20px;margin-top:22px"><h3 style="font-size:14px">Seuils des alertes de retard (heures)</h3><div class="form-grid">${input("alert_transit_hours","Palette envoyée non arrivée",S.settings.alert_transit_hours??"48","number",true,'min="0" max="720" step="1"')}${input("alert_partial_hours","Réception partielle en attente",S.settings.alert_partial_hours??"24","number",true,'min="0" max="720" step="1"')}${input("alert_unassigned_hours","Colis réceptionné non affecté",S.settings.alert_unassigned_hours??"24","number",true,'min="0" max="720" step="1"')}</div><p class="form-hint">0 désactive la catégorie. Les alertes se calculent dans la rubrique Alertes ; aucune notification externe n’est envoyée.</p></div><div class="form-actions"><button type="submit" class="btn primary">Enregistrer les paramètres</button></div></form></div>`
          : `${[
              [
                "mail",
                "E-mails transactionnels",
                "L’envoi des e-mails nécessite une configuration SMTP. La récupération de mot de passe par e-mail n’est pas activée.",
              ],
              [
                "phone",
                "WhatsApp Business",
                "Une connexion à l’API officielle WhatsApp Business et des modèles de messages approuvés sont nécessaires.",
              ],
              [
                "link",
                "Google & Google Sheets",
                "L’authentification Google et la synchronisation Sheets nécessitent un projet OAuth. Elles ne sont pas activées dans cette version.",
              ],
            ]
              .map(
                ([i, t, p]) =>
                  `<div class="integration"><span class="stat-icon">${icon(i)}</span><div><div class="flex" style="margin-bottom:8px"><h3>${t}</h3><span class="tag">Non connecté</span></div><p>${p}</p></div></div>`,
              )
              .join("")}`
    }</div>`
  );
}
function cityForm(id) {
  const c = S.cities.find((c) => c.id === id) || {
    name: "",
    region: "Oriental",
    fee: 30,
    return_fee: 10,
    delivery: 1,
    pickup: 1,
  };
  modal(
    id ? "Modifier la ville" : "Étendre votre couverture",
    form(
      `${input("name", "Nom de la ville", c.name)}${input("region", "Région", c.region, "text", true, 'placeholder="Oriental, Fès-Meknès…"')}${input("fee", "Tarif livraison (MAD)", c.fee, "number", true, 'min="0" step="0.01"')}${input("return_fee", "Frais de retour (MAD)", c.return_fee, "number", true, 'min="0" step="0.01"')}<div class="switch"><input id="city-delivery" name="delivery" type="checkbox" ${c.delivery ? "checked" : ""}><label for="city-delivery">Livraison ouverte</label></div><div class="switch"><input id="city-pickup" name="pickup" type="checkbox" ${c.pickup ? "checked" : ""}><label for="city-pickup">Ramassage ouvert</label></div><div class="full form-hint orange">Une ville active en livraison apparaît sur le site public et dans le formulaire d’ajout de colis. Vous pouvez la désactiver sans perdre l’historique.</div>`,
    ),
  );
  bindForm(async (d) => {
    await api("/cities" + (id ? "/" + id : ""), id ? "PATCH" : "POST", d);
    await saved(id ? "Ville mise à jour" : "Nouvelle ville ajoutée");
  });
}
async function toggleCity(id, key, value) {
  try {
    const c = S.cities.find((c) => c.id === id);
    await api("/cities/" + id, "PATCH", { ...c, [key]: value });
    await refresh();
    await renderView();
    toast("Couverture mise à jour");
  } catch (e) {
    toast(e.message, true);
    await renderView();
  }
}
function bindSettings() {
  bindForm(async (d) => {
    await api("/settings", "PATCH", {...d,alert_transit_hours:Number(d.alert_transit_hours),alert_partial_hours:Number(d.alert_partial_hours),alert_unassigned_hours:Number(d.alert_unassigned_hours)});
    await refresh();
    toast("Paramètres enregistrés");
  }, "settings-form");
}
function profileView() {
  const u = S.user;
  return (
    heading(
      "Mon profil",
      "Vos informations et la sécurité de votre compte.",
      `<button class="btn" onclick="logout()">${icon("logout")}Se déconnecter</button>`,
    ) +
    `<section class="card profile-card"><div class="profile-avatar"><span class="avatar">${initials(u.name)}</span><div><h3>${esc(u.name)}</h3><span class="sub">${esc(u.email)} · ${u.role==='client'?clientTypeLabel(u):roleName(u.role)}</span></div></div><form id="profile-form"><div class="form-error"></div><div class="form-grid">${input("name", "Nom complet", u.name)}${input("phone", "Téléphone", u.phone, "tel")}${input("company", "Entreprise / Boutique", u.company, "text", false)}<div class="full" style="border-top:1px solid var(--line);padding-top:22px"><h3 style="font-size:14px">Changer mon mot de passe</h3><p class="sub">Laissez ces champs vides pour conserver votre mot de passe. Sur le serveur, le changement ferme toutes vos anciennes sessions et renouvelle celle-ci.</p></div>${input("current_password", "Mot de passe actuel", "", "password", false, 'autocomplete="current-password"')}${input("password", "Nouveau mot de passe", "", "password", false, 'minlength="10" autocomplete="new-password"')}</div><div class="form-actions"><button class="btn primary" type="submit">${icon("check")}Enregistrer mon profil</button></div></form></section>`
  );
}
function bindProfile() {
  bindForm(async (d) => {
    await api("/profile", "PATCH", d);
    await refresh();
    shell();
    await renderView();
    toast("Profil enregistré");
  }, "profile-form");
}
async function logout() {
  try {
    await api("/logout", "POST");
    S = null;
    if (typeof resetDriverFinance === "function") resetDriverFinance();
    $("#print-root").innerHTML = "";
    closeModal();
    renderLogin();
  } catch (e) {
    toast(e.message, true);
  }
}
function usersView() {
  const role = view === "drivers" ? "livreur" : "client",
    us = S.users.filter((u) => u.role === role);
  return (
    heading(
      role === "livreur" ? "Votre équipe de livreurs" : "Vos clients",
      role === "livreur"
        ? "Les visages derrière chaque livraison."
        : "Des partenaires qui font grandir votre réseau.",
      `<button class="btn primary" onclick="userForm(null,'${role}')">${icon("plus")}${role === "livreur" ? "Ajouter un livreur" : "Ajouter un client"}</button>`,
    ) +
    `<div class="card"><div class="card-head"><h3>${us.length} ${role === "livreur" ? "livreurs" : "clients"} enregistrés</h3><span class="tag good">${us.filter((u) => u.active).length} actifs</span></div><div class="table-wrap"><table><thead><tr><th>Nom</th><th>Coordonnées</th><th>${role === "client" ? "Entreprise / Type" : "Colis assignés"}</th><th>Statut</th><th></th></tr></thead><tbody>${us.map((u) => `<tr><td><div class="recipient"><span class="avatar">${initials(u.name)}</span><strong>${esc(u.name)}</strong></div></td><td>${esc(u.email)}<span class="sub">${esc(u.phone)}</span></td><td>${role === "client" ? `${esc(u.company)}<span class="sub">${clientTypeLabel(u)}</span>` : S.parcels.filter((p) => p.driver_id === u.id).length}</td><td><span class="tag ${u.active ? "good" : "bad"}">${u.active ? "Actif" : "Désactivé"}</span></td><td>${role === "client" ? `<button class="icon-btn" onclick="tariffForm(${u.id})" title="Tarifs par ville">${icon("wallet")}</button>${u.client_type === "societe_livraison" ? `<button class="icon-btn" onclick="apiKeysForm(${u.id},'${esc(u.company || u.name)}')" title="Clé API partenaire">${icon("scan")}</button>` : ""}` : ""}<button class="icon-btn" onclick="userForm(${u.id},'${role}')" title="Modifier le compte">${icon("edit")}</button></td></tr>`).join("")}</tbody></table></div>${!us.length ? empty("Votre réseau commence ici", "Créez votre premier compte.") : ""}</div>`
  );
}
function userForm(id, role) {
  const u = S.users.find((u) => u.id === id) || {
    name: "",
    email: "",
    phone: "",
    company: "",
    active: 1,
  };
  modal(
    id
      ? "Modifier le compte"
      : role === "livreur"
        ? "Nouveau livreur"
        : "Nouveau client",
    form(
      `${role === "client" ? select("client_type", "Type de client", clientTypeOptions, u.client_type || "vendeur") + `<div class="form-hint"><b>Vendeur</b> : tracking ORIENTAL24 automatique.<br><b>Société de livraison</b> : tracking saisi par la société et conservé.${id?"<br>Le type est verrouillé après le premier colis ou la première préparation.":""}</div>` : ""}${input("name", "Nom complet", u.name)}${!id ? input("email", "Adresse e-mail", "", "email") : `<div class="form-hint">${esc(u.email)}<br>L’identifiant du compte est conservé.</div>`}${input("phone", "Téléphone", u.phone, "tel")}${input("company", "Entreprise / Boutique", u.company, "text", false)}${input("password", id ? "Nouveau mot de passe (facultatif)" : "Mot de passe initial", "", "password", !id, 'minlength="10" autocomplete="new-password"')}${id ? `<div class="switch"><input id="user-active" type="checkbox" name="active" ${u.active ? "checked" : ""}><label for="user-active">Compte actif</label></div>` : ""}<div class="full form-hint">Minimum 10 caractères pour le mot de passe. ${id ? "Un compte désactivé ne peut plus accéder à la plateforme." : "Transmettez les identifiants au titulaire par un canal sûr."}</div>`,
    ),
  );
  bindForm(async (d) => {
    await api("/users" + (id ? "/" + id : ""), id ? "PATCH" : "POST", {
      ...d,
      role,
    });
    await saved("Compte enregistré");
  });
}
function analyticsView() {
  const drivers = S.users.filter((u) => u.role === "livreur");
  const ps = S.parcels,
    assigned = ps.filter((p) => p.driver_id),
    del = ps.filter((p) => p.status === "Livré"),
    ret = ps.filter((p) => ["Retourné", "Refusé"].includes(p.status));
  return (
    heading(
      "Statistiques & performance",
      "Une vision claire de votre activité et de vos équipes.",
      `<a class="btn" href="/api/export">${icon("download")}Exporter les colis</a>`,
    ) +
    `<section class="stats">${stat("Livreurs actifs", drivers.filter((u) => u.active).length, "", "users", "purple", "Comptes disponibles")}${stat("Colis assignés", assigned.length, "", "box", "blue", "Toutes périodes confondues")}${stat("Taux de livraison", ps.length ? Math.round((del.length / ps.length) * 100) : 0, "%", "checkcircle", "green", del.length + " colis livrés")}${stat("Retours & refus", ret.length, "", "return", "", ps.length ? Math.round((ret.length / ps.length) * 100) + "% du total" : "Aucun colis")}</section><div class="analytic-grid">${drivers
      .map((u) => {
        const pp = ps.filter((p) => p.driver_id === u.id),
          dd = pp.filter((p) => p.status === "Livré"),
          rate = pp.length ? Math.round((dd.length / pp.length) * 100) : 0;
        return `<article class="card driver-card"><div class="flex between"><span class="avatar orange">${initials(u.name)}</span><span class="tag ${u.active ? "good" : "bad"}">${u.active ? "Actif" : "Inactif"}</span></div><h3>${esc(u.name)}</h3><span class="sub">${esc(u.phone)}</span><div class="driver-metrics"><span>Assignés<b>${pp.length}</b></span><span>Livrés<b>${dd.length}</b></span><span>Taux<b>${rate}%</b></span></div><div class="bar"><span style="width:${rate}%"></span></div><div class="detail-line" style="margin-top:18px"><span>COD collecté</span><strong>${money(dd.reduce((s, p) => s + p.amount, 0))} MAD</strong></div></article>`;
      })
      .join("")}</div>`
  );
}
function simpleTable(headers, rows) {
  return rows.length
    ? `<div class="table-wrap"><table><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((v) => `<td>${v}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
    : empty();
}
function ticketsView(rows) {
  return (
    heading(
      "Réclamations",
      "Un échange, une solution. Suivez toutes vos demandes.",
      `<button class="btn primary" onclick="newTicket()">${icon("plus")}Nouvelle réclamation</button>`,
    ) +
    `<div class="card"><div class="card-head"><h3>Mes échanges</h3><span class="tag">${rows.length} tickets</span></div>${simpleTable(
      ["Ticket", "Sujet", "Auteur", "Catégorie", "Statut", "Créé le", ""],
      rows.map((t) => [
        `<span class="tracking">TKT-${String(t.id).padStart(4, "0")}</span>`,
        `<strong>${esc(t.subject)}</strong>${t.tracking?`<span class="sub">${esc(t.tracking)} · ${esc(t.priority)}</span>`:""}`,
        esc(t.author),
        esc(t.category),
        tag(t.status),
        date(t.created_at),
        `<button class="btn sm" onclick="ticketDetail(${t.id})">Ouvrir ${icon("chevron")}</button>`,
      ]),
    )}</div>`
  );
}
function newTicket() {
  modal(
    "Nouvelle réclamation",
    form(
      `${input("subject", "Objet")}${select(
        "category",
        "Catégorie",
        ["Livraison", "Ramassage", "Facturation", "Retour", "Autre"].map(
          (s) => [s, s],
        ),
      )}${textarea("body", "Votre message", "", true)}`,
      "Envoyer la réclamation",
    ),
  );
  bindForm(async (d) => {
    await api("/tickets", "POST", d);
    await saved("Réclamation envoyée");
  });
}
async function ticketDetail(id) {
  const owner=S?.user?.id;
  try {
    const d = await api("/tickets/" + id);
    if(S?.user?.id!==owner)return;
    modal(
      "TKT-" + String(id).padStart(4, "0") + " · " + d.ticket.subject,
      `<div class="flex between">${tag(d.ticket.status)}${S.user.role === "admin" ? `<select style="width:160px;font-size:12px" aria-label="Statut du ticket" onchange="setTicketStatus(${id},this.value)">${["Ouvert", "En cours", "Résolu"].map((s) => `<option ${s === d.ticket.status ? "selected" : ""}>${s}</option>`).join("")}</select>` : ""}</div>${d.ticket.parcel_id?`<div class="ops-ticket-context">Colis : ${esc(d.ticket.tracking)} · Priorité : ${esc(d.ticket.priority)}<br>Responsable : ${esc(S.users.find(u=>u.id===d.ticket.assigned_to)?.name|| (d.ticket.assigned_to?"Administration":"Non affecté"))}<br>Première réponse admin : ${opsDate(d.ticket.first_response_at)}${S.user.role==="admin"?`<button class="btn sm" onclick="opsTicketOwner(${id},'${d.ticket.priority}')">Affecter / Priorité</button>`:""}</div>`:""}${claimAttachmentsMarkup(d.attachments||[])}${d.messages.map((m) => `<div class="message ${m.role === "admin" ? "admin" : ""}"><b>${esc(m.author)}</b><small>${date(m.created_at)}</small><p>${esc(m.body)}</p></div>`).join("")}<form id="reply-form" style="margin-top:20px"><div class="form-error"></div>${textarea("body", "Votre réponse", "", true)}<div class="form-actions"><button class="btn primary" type="submit">Envoyer ${icon("arrow")}</button></div></form>`,
    );
    bindForm(async (f) => {
      await api("/tickets/" + id, "POST", f);
      await ticketDetail(id);
      toast("Réponse envoyée");
    }, "reply-form");
  } catch (e) {
    toast(e.message, true);
  }
}
async function setTicketStatus(id, status) {
  try {
    await api("/tickets/" + id, "PATCH", { status });
    await ticketDetail(id);
    await renderView();
    toast("Statut du ticket enregistré");
  } catch (e) {
    toast(e.message, true);
  }
}
function pickupsView(rows) {
  return (
    heading(
      "Ramassages",
      "Préparez vos colis. Nous organisons la suite.",
      `<button class="btn primary" onclick="newPickup()">${icon("plus")}Demander un ramassage</button>`,
    ) +
    `<section class="card"><div class="card-head"><h3>Demandes de ramassage</h3><span class="tag">${rows.length} demandes</span></div>${simpleTable(
      [
        "Référence",
        "Client",
        "Ville / Adresse",
        "Date prévue",
        "Colis",
        "Statut",
        "",
      ],
      rows.map((p) => [
        `<span class="tracking">RAM-${String(p.id).padStart(4, "0")}</span>`,
        esc(p.client),
        `<strong>${esc(p.city)}</strong><span class="sub">${esc(p.address)}</span>`,
        date(p.date),
        p.count,
        tag(p.status),
        S.user.role === "admin"
          ? `<select aria-label="Statut du ramassage" style="padding:6px;font-size:11px" onchange="updatePickup(${p.id},this.value)">${["Demandé", "Planifié", "Ramassé", "Annulé"].map((s) => `<option ${s === p.status ? "selected" : ""}>${s}</option>`).join("")}</select>`
          : "—",
      ]),
    )}</section>`
  );
}
function newPickup() {
  const cs = S.cities.filter((c) => c.pickup);
  const today = new Date();
  const localDate = [
    today.getFullYear(),
    String(today.getMonth() + 1).padStart(2, "0"),
    String(today.getDate()).padStart(2, "0"),
  ].join("-");
  modal(
    "Demander un ramassage",
    form(
      `${select("city_id", "Ville de ramassage", [["", "Choisir une ville"], ...cs.map((c) => [c.id, c.name])])}${input("date", "Date souhaitée", localDate, "date", true, `min="${localDate}"`)}${input("phone", "Téléphone", S.user.phone, "tel")}${input("count", "Nombre de colis", 1, "number", true, 'min="1" max="10000"')}${textarea("address", "Adresse de ramassage", "", true)}<div class="full form-hint">La demande sera confirmée par l’administration. Seules les villes ouvertes au ramassage sont proposées.</div>`,
      "Envoyer la demande",
    ),
  );
  bindForm(async (d) => {
    await api("/pickups", "POST", d);
    await saved("Demande de ramassage envoyée");
  });
}
async function updatePickup(id, status) {
  try {
    await api("/pickups/" + id, "PATCH", { status });
    await renderView();
    toast("Ramassage mis à jour");
  } catch (e) {
    toast(e.message, true);
  }
}
function palletsView(rows) {
  return (
    heading(
      "Palettes",
      "Gardez une trace de vos transferts entre hubs.",
      `<button class="btn primary" onclick="newPallet()">${icon("plus")}Envoyer une palette</button>`,
    ) +
    `<div class="demo-notice">Ancien registre déclaratif, sans manifeste de colis. Pour les envois des sociétés de livraison, utilisez Palettes partenaires : leur réception s’effectue uniquement dans ce nouveau parcours.</div><section class="card"><div class="card-head"><h3>Transferts inter-hubs</h3><span class="tag">${rows.length} palettes</span></div>${simpleTable(
      [
        "Code",
        "Source",
        "Destination",
        "Transport",
        "Nombre de colis",
        "Statut",
        "",
      ],
      rows.map((p) => [
        `<span class="tracking">${esc(p.code)}</span>`,
        esc(p.source),
        esc(p.destination),
        esc(p.transport),
        p.count,
        tag(p.status),
        p.status !== "Réceptionnée"
          ? `<button class="btn sm" onclick="receivePallet(${p.id})">${icon("download")}Réceptionner</button>`
          : `<span class="green">${icon("checkcircle")}</span>`,
      ]),
    )}</section>`
  );
}
function newPallet() {
  modal(
    "Nouvelle palette",
    form(
      `${input("source", "Hub de départ", "", "text", true, 'placeholder="Hub Oujda"')}${input("destination", "Hub de destination", "", "text", true, 'placeholder="Hub Berkane"')}${input("transport", "Transport / Navette")}${input("count", "Nombre de colis", 1, "number", true, 'min="1"')}`,
      "Créer la palette",
    ),
  );
  bindForm(async (d) => {
    await api("/pallets", "POST", d);
    await saved("Palette créée");
  });
}
function receivePallet(id) {
  modal(
    "Confirmer la réception",
    form(
      '<div class="full form-hint">Confirmez uniquement après vérification physique de la palette et de son contenu.</div>',
      "Confirmer la réception",
    ),
  );
  bindForm(async () => {
    await api("/pallets/" + id, "PATCH", {});
    await saved("Palette réceptionnée");
  });
}
let invoiceRows = [];
function invoicesView(rows) {
  invoiceRows = rows;
  const due = rows
      .filter((i) => i.status !== "Réglée")
      .reduce((s, i) => s + i.total, 0),
    paid = rows
      .filter((i) => i.status === "Réglée")
      .reduce((s, i) => s + i.total, 0);
  return (
    heading(
      "Facturation",
      "Vos encaissements et vos règlements, en toute transparence.",
      S.user.role === "admin"
        ? `<button class="btn primary" onclick="newInvoice()">${icon("plus")}Générer une facture</button>`
        : "",
    ) +
    `<section class="stats">${stat("Montant COD", money(rows.reduce((s, i) => s + i.cod, 0)), "MAD", "wallet", "blue", "Colis facturés")}${stat("Frais de service", money(rows.reduce((s, i) => s + i.fees, 0)), "MAD", "file", "", "Livraisons & retours")}${stat("Net à régler", money(due), "MAD", "clock", "purple", "Solde des factures ouvertes")}${stat("Net réglé", money(paid), "MAD", "checkcircle", "green", "Règlements enregistrés")}</section><div class="card"><div class="card-head"><h3>Relevés de facturation</h3><span class="tag">${rows.length} factures</span></div>${simpleTable(
      [
        "Facture",
        "Client",
        "Montant COD",
        "Frais",
        "Net",
        "Statut",
        "Date",
        "",
      ],
      rows.map((i) => [
        `<span class="tracking">FAC-${String(i.id).padStart(4, "0")}</span>`,
        esc(i.company || i.client),
        money(i.cod) + " MAD",
        money(i.fees) + " MAD",
        `<strong>${money(i.total)} MAD</strong>`,
        tag(i.status),
        date(i.created_at),
        `<button class="icon-btn" onclick="invoiceDetail(${i.id})" title="Consulter la facture">${icon("file")}</button>`,
      ]),
    )}</div>`
  );
}
function newInvoice() {
  modal(
    "Générer un relevé client",
    form(
      `${select("client_id", "Client", clientOptions())}<div class="full form-hint">Regroupe tous les colis livrés, retournés ou refusés non encore facturés pour ce client. Le net est égal au COD des colis livrés moins les frais de livraison et de retour.</div><div class="full form-hint orange">Les colis inclus seront verrouillés pour éviter de modifier un montant déjà facturé.</div>`,
      "Générer la facture",
    ),
  );
  bindForm(async (d) => {
    await api("/invoices", "POST", d);
    billingReset("client");
    await refresh();closeModal();await navigate("invoices");toast("Facture générée · disponible dans Facturation");
  });
}
async function invoiceDetail(id) {
  try {
    const d = await api("/invoices/" + id),
      i = d.invoice;
    modal(
      "FAC-" + String(id).padStart(4, "0"),
      `<div class="flex between" style="margin-bottom:20px"><div><h3>${esc(i.company || i.client)}</h3><span class="sub">${date(i.created_at)}</span></div>${tag(i.status)}</div>${simpleTable(
        ["Colis", "Statut", "COD", "Frais"],
        d.parcels.map((p) => [
          esc(p.tracking),
          tag(p.status),
          money(p.status === "Livré" ? p.amount : 0) + " MAD",
          money(p.status === "Livré" ? p.fee : p.return_fee) + " MAD",
        ]),
      )}<div class="detail-info" style="margin-top:20px"><div class="detail-line"><span>COD collecté</span><strong>${money(i.cod)} MAD</strong></div><div class="detail-line"><span>Frais de service</span><span>− ${money(i.fees)} MAD</span></div><div class="detail-line"><strong>Net ${i.total >= 0 ? "à reverser au client" : "dû par le client"}</strong><strong>${money(Math.abs(i.total))} MAD</strong></div></div><div class="form-actions"><button class="btn" onclick="printInvoice(${id})">${icon("print")}Imprimer / PDF</button>${S.user.role === "admin" && i.status !== "Réglée" ? `<button class="btn primary" onclick="payInvoice(${id})">${icon("check")}Enregistrer le règlement</button>` : ""}</div>`,
      true,
    );
  } catch (e) {
    toast(e.message, true);
  }
}
function payInvoice(id) {
  modal(
    "Confirmer le règlement",
    form(
      '<div class="full form-hint orange">Cette action enregistre un règlement déjà effectué. Elle ne déclenche aucun virement bancaire. Vérifiez le paiement avant de confirmer.</div>',
      "Confirmer le règlement",
    ),
  );
  bindForm(async () => {
    await api("/invoices/" + id, "PATCH", {});
    await saved("Règlement enregistré");
  });
}
let productRows = [];
function stockView(rows, requests, movements) {
  return stockOperationsView(rows, requests, movements);
}
function newProduct() {
  modal(
    "Nouveau produit",
    form(
      `${S.user.role === "admin" ? select("client_id", "Client", clientOptions()) : ""}${input("name", "Nom du produit")}${input("reference", "Référence SKU")}<div class="full form-hint">Le stock initial est de zéro. L’administration enregistre les quantités reçues dans les mouvements de stock.</div>`,
    ),
  );
  bindForm(async (d) => {
    await api("/products", "POST", d);
    await saved("Produit créé");
  });
}
async function productDetail(id) {
  try {
    const p = productRows.find((p) => p.id === id),
      rows = await api("/products/" + id + "/movements");
    modal(
      p.name,
      `<div class="flex between" style="margin-bottom:20px"><span class="mono">${esc(p.reference)}</span><span class="tag good">${p.available ?? p.quantity} disponibles · ${p.reserved ?? 0} réservées · ${p.quantity} physiques</span></div>${simpleTable(
        ["Date", "Mouvement", "Motif", "Auteur"],
        rows.map((m) => [
          date(m.created_at),
          `<strong class="${m.delta > 0 ? "green" : "orange"}">${m.delta > 0 ? "+" : ""}${m.delta}</strong>`,
          esc(m.note),
          esc(m.actor),
        ]),
      )}<div class="form-actions"><button class="btn" onclick="newStockRequest(${id})">${icon("return")}Demander une entrée / sortie</button></div>${S.user.role === "admin" ? `<form id="movement-form" style="margin-top:24px"><div class="form-error"></div><div class="form-grid">${input("delta", "Quantité (+ entrée / − sortie)", "", "number", true, 'step="1"')}${input("note", "Motif du mouvement")}</div><div class="form-actions"><button class="btn primary" type="submit">Enregistrer le mouvement</button></div></form>` : ""}`,
    );
    if (S.user.role === "admin")
      bindForm(async (d) => {
        await api("/products/" + id + "/movements", "POST", d);
        await saved("Mouvement enregistré");
      }, "movement-form");
  } catch (e) {
    toast(e.message, true);
  }
}
function requestsView(rows) {
  return (
    heading(
      "Demandes de modification",
      "Les changements de prix passent par une validation.",
      `<button class="btn" onclick="navigate('parcels')">${icon("box")}Ouvrir un colis</button>`,
    ) +
    `<section class="card"><div class="card-head"><h3>Demandes de changement de prix</h3><span class="tag">${rows.length} demandes</span></div>${simpleTable(
      [
        "Demande",
        "Colis",
        "Demandeur",
        "Montant demandé",
        "Motif",
        "Statut",
        "",
      ],
      rows.map((r) => [
        `<span class="tracking">DEM-${String(r.id).padStart(4, "0")}</span>`,
        esc(r.tracking),
        esc(r.author),
        `<strong>${money(r.amount)} MAD</strong>`,
        esc(r.reason),
        tag(r.status),
        S.user.role === "admin" && r.status === "En attente"
          ? `<div class="flex"><button class="btn sm" onclick="decideRequest(${r.id},true)">${icon("check")}Accepter</button><button class="btn sm danger" onclick="decideRequest(${r.id},false)">Refuser</button></div>`
          : "—",
      ]),
    )}</section><p class="sub" style="margin-top:18px">Pour créer une demande, ouvrez un colis non clôturé puis choisissez « Demande de prix ».</p>`
  );
}
function decideRequest(id, accept) {
  modal(
    accept ? "Accepter le nouveau prix ?" : "Refuser la demande ?",
    form(
      `<div class="full form-hint">${accept ? "Le montant COD du colis sera modifié et une entrée sera ajoutée à son historique." : "Le montant du colis restera inchangé."}</div>`,
      accept ? "Accepter" : "Refuser",
    ),
  );
  bindForm(async () => {
    await api("/requests/" + id, "PATCH", {
      status: accept ? "Acceptée" : "Refusée",
    });
    await saved("Demande traitée");
  });
}
function printView() {
  return (
    heading(
      "Centre d’impression",
      "Préparez vos étiquettes et vos documents d’expédition.",
      `<button class="btn primary" onclick="printSelected()">${icon("print")}Imprimer la sélection</button>`,
    ) +
    `<div class="demo-notice">Étiquettes avec QR code et code-barres Code 128, formats A6 ou thermique. Sélectionnez jusqu’à 50 colis, vérifiez l’aperçu, puis imprimez ou enregistrez au format PDF.</div><section class="card"><div class="card-head"><h3>Étiquettes des colis</h3><span class="tag">${S.parcels.length} colis</span></div>${parcelTable(S.parcels)}</section>`
  );
}
function printSelected() {
  const ids = [...document.querySelectorAll(".parcel-select:checked")].map(
    (x) => Number(x.value),
  );
  if (!ids.length) {
    toast("Sélectionnez au moins un colis à imprimer.", true);
    return;
  }
  printLabels(ids);
}
async function doPrint(html, prepare = null) {
  $("#print-root").innerHTML = html;
  await Promise.all(
    [...$("#print-root").querySelectorAll("img")].map((img) => img.decode()),
  );
  await new Promise((resolve) =>
    requestAnimationFrame(() => requestAnimationFrame(resolve)),
  );
  if (prepare) { await document.fonts.ready; await prepare($("#print-root")); }
  window.print();
}
function printLabels(ids) {
  return previewLabels(ids);
}
async function printInvoice(id) {
  const owner=S?.user?.id;
  try {
    const data=await api('/billing/client/'+id);
    if(S?.user?.id!==owner)return;
    const printData=clientInvoicePrintData(data);
    await doPrint(driverInvoicePrintHTML(printData),(root)=>{
      if(S?.user?.id!==owner){root.innerHTML='';throw Error('Session modifiée. Rouvrez la facture.');}
      paginateDriverInvoice(root,printData);
    });
  } catch(e) {if(S?.user?.id===owner)toast(e.message,true);}
}
async function boot() {
  if (location.pathname === "/app") {
    try {
      await refresh();
      shell();
      await renderView();
    } catch {
      renderLogin();
    }
  } else if (location.pathname === "/login") {
    renderLogin();
  } else {
    await renderPublic();
  }
}
function driverCards(rows) {
  return `<div class="driver-mobile-list">${rows.map((p) => `<article class="delivery-card"><div class="flex between"><button class="tracking" onclick="parcelDetail(${p.id})">${esc(p.tracking)}</button>${tag(p.status)}</div><div class="parcel-copy-recipient">${parcelCopyButton(p)}<h3>${esc(p.recipient)}</h3></div><p>${esc(p.address)} · ${esc(p.city)}</p><div class="flex between"><span class="amount">${money(p.amount)} <small>MAD</small></span><a class="btn sm" style="width:auto;margin:0" href="tel:${esc(p.phone.replace(/[^+\d]/g, ""))}">${icon("phone")}Appeler</a></div><button class="btn ${p.invoice_id || p.financial_locked || p.operations_locked || ["Livré", "Retourné"].includes(p.status) ? "" : "primary"}" onclick="${p.invoice_id || p.financial_locked || p.operations_locked || ["Livré", "Retourné"].includes(p.status) ? "parcelDetail" : "changeStatus"}(${p.id})">${icon("box")}${p.invoice_id || p.financial_locked || p.operations_locked || ["Livré", "Retourné"].includes(p.status) ? "Voir le colis" : "Mettre à jour le colis"}</button><div class="driver-note-row">${parcelStatusControl(p)}${parcelNoteControl(p)}</div>${parcelClaimButton(p,true)}</article>`).join("")}</div>`;
}
