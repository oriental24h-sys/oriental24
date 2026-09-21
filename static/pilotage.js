/* ORIENTAL24 — UX improvements informed by the September 2026 product review.
   Read-only operational queues and filters: never alter status or accounting rules. */
const parcelQueues = {
  unassigned: {
    title: "À affecter",
    detail: "Colis ouverts sans livreur",
    icon: "user",
    roles: ["admin"],
    test: (p) =>
      !p.driver_id && !["Livré", "Retourné", "Refusé"].includes(p.status),
  },
  delivery: {
    title: "En livraison",
    detail: "Colis actuellement en livraison",
    icon: "truck",
    roles: ["admin", "client", "livreur"],
    test: (p) => p.status === "En livraison",
  },
  scheduled: {
    title: "Programmés",
    detail: "À consulter avant la prochaine action",
    icon: "calendar",
    roles: ["admin", "client", "livreur"],
    test: (p) => p.status === "Programmé",
  },
  exceptions: {
    title: "Retours & refus",
    detail: "Statuts à examiner, sans présumer un incident",
    icon: "return",
    roles: ["admin", "client", "livreur"],
    test: (p) => ["Retourné", "Refusé"].includes(p.status),
  },
  uninvoiced: {
    title: "À facturer",
    detail: "Clôturés sans relevé client",
    icon: "wallet",
    roles: ["admin", "client"],
    test: (p) =>
      ["Livré", "Retourné", "Refusé"].includes(p.status) && !p.invoice_id,
  },
  driverOpen: {
    title: "À rapprocher",
    detail: "Clôturés sans relevé livreur",
    icon: "wallet",
    roles: ["livreur"],
    test: (p) =>
      ["Livré", "Retourné", "Refusé"].includes(p.status) && !p.financial_locked,
  },
};
function queueAllowed(key) {
  return parcelQueues[key]?.roles.includes(S.user.role);
}
function parcelText(v) {
  return String(v ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("fr");
}
function freshParcelFilters() {
  return {
    q: "",
    status: "",
    city: "",
    from: "",
    to: "",
    driver: "",
    client: "",
    billing: "",
    queue: "",
    reason: "",
  };
}
function filteredParcels() {
  if (filters.from && filters.to && filters.from > filters.to) return [];
  const q = parcelText(filters.q).trim();
  return S.parcels.filter(
    (p) =>
      (!q ||
        [
          p.tracking,
          p.recipient,
          p.phone,
          p.company,
          p.client,
          p.city,
          p.driver,
          p.product,
        ].some((x) => parcelText(x).includes(q))) &&
      (!filters.status || p.status === filters.status) &&
      (!filters.reason || (filters.reason === "__none" ? !p.reason_code : p.reason_code === filters.reason)) &&
      (!filters.city || String(p.city_id) === String(filters.city)) &&
      (!filters.from || p.created_at.slice(0, 10) >= filters.from) &&
      (!filters.to || p.created_at.slice(0, 10) <= filters.to) &&
      (!filters.driver ||
        (filters.driver === "none"
          ? !p.driver_id
          : String(p.driver_id) === String(filters.driver))) &&
      (!filters.client || String(p.client_id) === String(filters.client)) &&
      (!filters.queue ||
        (queueAllowed(filters.queue) && parcelQueues[filters.queue].test(p))) &&
      (!filters.billing ||
        {
          invoiced: !!p.invoice_id,
          uninvoiced: !p.invoice_id,
          driverLocked: !!p.financial_locked,
          driverOpen: !p.financial_locked,
        }[filters.billing]),
  );
}
function setParcelFilter(key, value) {
  filters[key] = value;
  listPage = 1;
  drawParcelTable();
}
function resetParcelFilters() {
  filters = freshParcelFilters();
  listPage = 1;
  renderView();
}
function setParcelTab(status) {
  filters.status = status;
  filters.queue = "";
  listPage = 1;
  renderView();
}
async function openParcelQueue(key) {
  if (!queueAllowed(key)) return;
  filters = { ...freshParcelFilters(), queue: key };
  await navigate("parcels");
}
function pilotageQueues() {
  const rows = Object.entries(parcelQueues).filter(([key]) =>
    queueAllowed(key),
  );
  return `<section class="pilotage-section" aria-label="Raccourcis opérationnels"><div class="pilotage-section-title"><div><span class="eyebrow orange">PASSER À L’ACTION</span><h2>${S.user.role === "livreur" ? "Votre tournée, par priorité de consultation" : "Les files à consulter"}</h2></div><p>Dernière actualisation · Toutes périodes</p></div><div class="pilotage-queues">${rows
    .map(([key, q]) => {
      const count = S.parcels.filter(q.test).length;
      return `<button class="pilotage-queue ${count ? "has-items" : ""}" onclick="openParcelQueue('${key}')"><div><span class="pilotage-queue-icon">${icon(q.icon)}</span><strong>${count}</strong></div><h3>${q.title}</h3><p>${q.detail}</p><span class="pilotage-queue-link">Voir les colis ${icon("arrow")}</span></button>`;
    })
    .join(
      "",
    )}</div><p class="pilotage-small-note">Ces compteurs décrivent les statuts enregistrés : ils ne mesurent ni un retard contractuel, ni un paiement bancaire.</p></section>`;
}
const dashboardBeforePilotage = dashboard;
dashboard = function () {
  const original = dashboardBeforePilotage()
    .replace(
      "Voici ce qui se passe chez ORIENTAL24 aujourd’hui.",
      "Votre activité enregistrée, toutes périodes confondues.",
    )
    .replace("Montant collecté", "COD livré déclaré");
  return original.replace(
    '<section class="two-col">',
    pilotageQueues() + '<section class="two-col">',
  );
};
parcelsView = function () {
  const admin = S.user.role === "admin",
    driver = S.user.role === "livreur",
    create = !driver;
  const option = (v, label, current) =>
    `<option value="${esc(v)}" ${String(v) === String(current || "") ? "selected" : ""}>${esc(label)}</option>`;
  const users = (role) =>
    S.users
      .filter((u) => u.role === role)
      .map((u) =>
        option(
          u.id,
          u.name + (u.active ? "" : " · inactif"),
          filters[role === "livreur" ? "driver" : "client"],
        ),
      )
      .join("");
  const billOptions = driver
    ? [
        ["driverOpen", "Sans relevé livreur"],
        ["driverLocked", "Avec relevé livreur"],
      ]
    : [
        ["uninvoiced", "Non facturés au client"],
        ["invoiced", "Facturés au client"],
        ...(admin
          ? [
              ["driverOpen", "Sans relevé livreur"],
              ["driverLocked", "Avec relevé livreur"],
            ]
          : []),
      ];
  return (
    heading(
      driver ? "Mes colis" : "Gestion des colis",
      "Retrouvez la bonne liste, puis agissez sur les colis concernés.",
      `<button class="btn export-btn" onclick="exportFilteredParcels()">${icon("download")}Exporter cette vue</button>${create ? `<button class="btn import-trigger" onclick="openImports()">${icon("upload")}Importer</button><button class="btn primary" onclick="newParcel()">${icon("plus")}Nouveau colis</button>` : ""}`,
    ) +
    `<section class="card pilotage-parcels"><div class="tabs" role="group" aria-label="Raccourcis de statut">${[
      ["", "Tous les colis"],
      ["En livraison", "En livraison"],
      ["Livré", "Livrés"],
      ["Programmé", "Programmés"],
      ["Retourné", "Retournés"],
      ["Refusé", "Refusés"],
    ]
      .map(
        ([s, label]) =>
          `<button class="${(filters.status || "") === s && !filters.queue ? "active" : ""}" aria-pressed="${(filters.status || "") === s && !filters.queue}" onclick="${s ? `setParcelTab('${s}')` : "resetParcelFilters()"}">${label}<span class="pilotage-tab-count">${s ? S.parcels.filter((p) => p.status === s).length : S.parcels.length}</span></button>`,
      )
      .join(
        "",
      )}</div><div class="toolbar"><div class="search-field">${icon("search")}<input id="parcel-search" aria-label="Rechercher un colis" placeholder="Référence, nom, téléphone, boutique…" value="${esc(filters.q || "")}" oninput="setParcelFilter('q',this.value)"></div><select id="status-filter" aria-label="Filtrer par statut" onchange="setParcelFilter('status',this.value)"><option value="">Tous les statuts</option>${S.statuses.map((s) => option(s, s, filters.status)).join("")}</select><select id="pilotage-city" aria-label="Filtrer par ville" onchange="setParcelFilter('city',this.value)"><option value="">Toutes les villes</option>${S.cities.map((c) => option(c.id, c.name, filters.city)).join("")}</select><select id="reason-filter" aria-label="Filtrer par motif" onchange="setParcelFilter('reason',this.value)"><option value="">Tous les motifs</option>${option("__none","Sans motif",filters.reason)}${[...new Map(S.parcels.filter(p=>p.reason_code).map(p=>[p.reason_code,p.reason_label||p.reason_code])).entries()].map(([code,label])=>option(code,label,filters.reason)).join("")}</select><div class="spacer"></div><button class="btn sm" onclick="openScanner()">${icon("scan")}Scanner</button><button class="btn sm" onclick="printSelected()">${icon("print")}Étiquettes</button><button class="icon-btn" onclick="resetParcelFilters()" title="Réinitialiser les filtres">${icon("return")}</button><button class="icon-btn" onclick="reloadView()" title="Actualiser les données">${icon("refresh")}</button></div><div class="pilotage-filters"><div><label for="pilotage-from">Créés du</label><input id="pilotage-from" type="date" value="${esc(filters.from || "")}" onchange="setParcelFilter('from',this.value)"></div><div><label for="pilotage-to">Créés au (inclus)</label><input id="pilotage-to" type="date" value="${esc(filters.to || "")}" onchange="setParcelFilter('to',this.value)"></div>${admin ? `<div><label for="pilotage-driver">Livreur actuel</label><select id="pilotage-driver" onchange="setParcelFilter('driver',this.value)"><option value="">Tous les livreurs</option>${option("none", "Sans affectation", filters.driver)}${users("livreur")}</select></div><div><label for="pilotage-client">Client / Boutique</label><select id="pilotage-client" onchange="setParcelFilter('client',this.value)"><option value="">Tous les clients</option>${users("client")}</select></div>` : ""}<div><label for="pilotage-billing">${driver ? "Rapprochement livreur" : "Facturation / rapprochement"}</label><select id="pilotage-billing" onchange="setParcelFilter('billing',this.value)"><option value="">Tous les colis</option>${billOptions.map(([v, label]) => option(v, label, filters.billing)).join("")}</select></div></div><div id="pilotage-filter-summary" aria-live="polite"></div><div id="parcel-table"></div></section><p class="pilotage-small-note">Les dates filtrent la date de création enregistrée, pas la date de livraison. L’export reprend tous les résultats filtrés, même sur plusieurs pages. Les cases de sélection concernent la page affichée.</p>`
  );
};
function parcelPagination(page, pages) {
  const set = new Set(
    [1, pages, page - 1, page, page + 1].filter((p) => p >= 1 && p <= pages),
  );
  let prev = 0;
  return [...set]
    .sort((a, b) => a - b)
    .map((i) => {
      const gap =
        i - prev > 1 ? '<span class="pilotage-ellipsis">…</span>' : "";
      prev = i;
      return (
        gap +
        `<button class="${page === i ? "active" : ""}" onclick="listPage=${i};drawParcelTable()" aria-label="Page ${i}">${i}</button>`
      );
    })
    .join("");
}
drawParcelTable = function () {
  if (!$("#parcel-table")) return;
  const rows = filteredParcels(),
    pages = Math.max(1, Math.ceil(rows.length / 10));
  listPage = Math.max(1, Math.min(listPage, pages));
  const badDates = filters.from && filters.to && filters.from > filters.to;
  const chips = [];
  if (filters.queue && queueAllowed(filters.queue))
    chips.push(["queue", parcelQueues[filters.queue].title]);
  if (filters.q) chips.push(["q", "Recherche : " + filters.q]);
  if (filters.status) chips.push(["status", filters.status]);
  if (filters.city)
    chips.push([
      "city",
      S.cities.find((c) => String(c.id) === String(filters.city))?.name ||
        "Ville",
    ]);
  if (filters.from) chips.push(["from", "Du " + date(filters.from)]);
  if (filters.to) chips.push(["to", "Au " + date(filters.to)]);
  if (filters.driver)
    chips.push([
      "driver",
      filters.driver === "none"
        ? "Sans affectation"
        : S.users.find((u) => String(u.id) === String(filters.driver))?.name ||
          "Livreur",
    ]);
  if (filters.client)
    chips.push([
      "client",
      S.users.find((u) => String(u.id) === String(filters.client))?.company ||
        "Client",
    ]);
  if (filters.reason) chips.push(["reason", "Motif : "+(filters.reason==="__none"?"Sans motif":S.parcels.find(p=>p.reason_code===filters.reason)?.reason_label||filters.reason)]);
  if (filters.billing)
    chips.push([
      "billing",
      {
        invoiced: "Facturés au client",
        uninvoiced: "Non facturés au client",
        driverLocked: "Avec relevé livreur",
        driverOpen: "Sans relevé livreur",
      }[filters.billing],
    ]);
  if ($("#pilotage-filter-summary"))
    $("#pilotage-filter-summary").innerHTML =
      `${badDates ? '<div class="pilotage-date-error" role="alert">La date de début doit précéder ou être égale à la date de fin.</div>' : ""}<div class="pilotage-filter-summary"><div class="pilotage-filter-chips">${chips.map(([key, label]) => `<button onclick="filters['${key}']='';listPage=1;renderView()" title="Retirer ce filtre">${esc(label)}${icon("close")}</button>`).join("") || "<span>Aucun filtre · Tous les colis de votre périmètre</span>"}</div><strong>${rows.length} résultat${rows.length !== 1 ? "s" : ""}</strong></div>`;
  document
    .querySelectorAll(".pilotage-parcels .tabs button")
    .forEach((button, index) => {
      const status = [
        "",
        "En livraison",
        "Livré",
        "Programmé",
        "Retourné",
        "Refusé",
      ][index];
      const active = !filters.queue && (filters.status || "") === status;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  $("#parcel-table").innerHTML =
    parcelTable(rows.slice((listPage - 1) * 10, listPage * 10)) +
    `<div class="table-footer"><span>${rows.length ? (listPage - 1) * 10 + 1 : 0}–${Math.min(rows.length, listPage * 10)} sur ${rows.length} colis</span><div class="pagination"><button onclick="listPage=Math.max(1,listPage-1);drawParcelTable()" ${listPage === 1 ? "disabled" : ""} aria-label="Page précédente">‹</button>${parcelPagination(listPage, pages)}<button onclick="listPage=Math.min(${pages},listPage+1);drawParcelTable()" ${listPage === pages ? "disabled" : ""} aria-label="Page suivante">›</button></div></div>`;
};
function parcelCsvCell(v) {
  let s = String(v ?? "");
  if (s.trimStart().match(/^[=+@-]/)) s = "'" + s;
  return '"' + s.replaceAll('"', '""') + '"';
}
function exportFilteredParcels() {
  if (filters.from && filters.to && filters.from > filters.to) {
    toast("Corrigez la période avant d’exporter.", true);
    return;
  }
  const rows = filteredParcels();
  if (!rows.length) {
    toast("Aucun résultat à exporter.", true);
    return;
  }
  const data = [
    [
      "Référence",
      "Destinataire",
      "Téléphone",
      "Ville",
      "Client / Boutique",
      "Livreur actuel",
      "Statut",
      "COD prévu MAD",
      "Frais livraison MAD",
      "Facturé client",
      "Relevé livreur actif",
      "Créé le",
      "Motif de suivi",
    ],
    ...rows.map((p) => [
      p.tracking,
      p.recipient,
      p.phone,
      p.city,
      p.company || p.client,
      p.driver || "",
      p.status,
      Number(p.amount).toFixed(2),
      Number(p.fee).toFixed(2),
      p.invoice_id ? "Oui" : "Non",
      p.financial_locked ? "Oui" : "Non",
      p.created_at,
      p.reason_label || p.reason_code || "",
    ]),
  ];
  const csv =
    "\ufeff" + data.map((row) => row.map(parcelCsvCell).join(";")).join("\r\n");
  const url = URL.createObjectURL(
      new Blob([csv], { type: "text/csv;charset=utf-8" }),
    ),
    link = document.createElement("a");
  link.href = url;
  link.download = "ORIENTAL24-colis-filtres.csv";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast(`${rows.length} colis dans l’export filtré`);
}
