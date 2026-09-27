/* ORIENTAL24 · opérations v1.1 — no external services or CDN dependencies. */
paths.scan =
  "M8 3H3v5 M16 3h5v5 M21 16v5h-5 M8 21H3v-5 M3 12h18 M8 7v3 M12 7v3 M16 7v3 M8 14v3 M12 14v3 M16 14v3";
paths.upload = "M12 17V3 M7 8l5-5 5 5 M4 16v5h16v-5";
let stockTab = "products",
  stockRequestRows = [],
  stockMovementRows = [],
  stockFilter = "all";
let importPreview = null,
  importOnlyErrors = false,
  importPage = 1;
let labelPreview = null;

async function uploadApi(url, data) {
  const response = await fetch("/api" + url, {
    method: "POST",
    headers: { "X-CSRF-Token": S.csrf },
    body: data,
  });
  const result = await response
    .json()
    .catch(() => ({ error: "Le fichier n’a pas pu être traité. Réessayez." }));
  if (!response.ok) throw Error(result.error || "Échec de l’import.");
  return result;
}
function importSteps(step) {
  return `<div class="import-steps">${[
    ["1", "Choisir le fichier"],
    ["2", "Vérifier les lignes"],
    ["3", "Créer les colis"],
  ]
    .map(
      ([n, t]) =>
        `<span class="${+n === step ? "current" : +n < step ? "complete" : ""}"><i>${+n < step ? icon("check") : n}</i>${t}</span>`,
    )
    .join("")}</div>`;
}
async function openImports() {
  try {
    const history = await api("/imports");
    modal(
      "Importer des colis",
      `${importSteps(1)}<div class="import-start"><div><h3>Plus de colis. Moins de saisie.</h3><p class="muted">Importez vos commandes en une fois. Vous vérifiez chaque ligne avant de confirmer.</p><form id="upload-import"><div class="form-error" role="alert"></div>${S.user.role === "admin" ? select("client_id", "Client destinataire de l’import", clientOptions()) : `<div class="import-account">${icon("user")}Import pour <strong>${esc(S.user.company || S.user.name)}</strong></div>`}<label class="upload-drop" id="upload-drop" for="import-file"><span class="stat-icon">${icon("upload")}</span><strong id="upload-file-name">Glissez votre fichier ici</strong><span id="upload-file-meta">ou cliquez pour parcourir vos fichiers</span><small>.xlsx ou .csv UTF-8 · 500 lignes · moins de 2 Mo</small><input id="import-file" type="file" name="file" accept=".xlsx,.csv" required aria-label="Fichier de colis"></label><button class="btn primary import-submit" type="submit">Vérifier mon fichier ${icon("arrow")}</button></form><div class="import-privacy">${icon("shield")}Aucun colis n’est créé sans votre confirmation.</div></div><aside class="import-guide"><div class="eyebrow">Bien préparer votre fichier</div><h3>Partez du bon modèle.</h3><p>Les villes ouvertes et leurs tarifs sont actualisés à chaque téléchargement du modèle Excel.</p><a href="/api/imports/template.xlsx" class="btn navy">${icon("download")}Modèle Excel .xlsx</a><a href="/api/imports/template.csv" class="section-link">Télécharger le modèle CSV ${icon("arrow")}</a><ul><li><b>Vendeur :</b> référence externe de commande ; tracking ORIENTAL24 automatique.</li><li><b>Société de livraison :</b> mettez votre tracking dans <code>reference_externe</code>. Il est conservé tel quel, unique sur la plateforme. Cellule texte pour garder les zéros.</li><li>Téléphones au format texte pour garder le zéro initial.</li><li>Remplacez la ligne d’exemple avant l’envoi.</li><li>Si une ligne est invalide, le lot entier attend votre correction.</li></ul></aside></div><div class="import-history"><div class="flex between"><h3>Mes derniers imports</h3><span class="sub">20 derniers lots</span></div>${
        history.length
          ? simpleTable(
              ["Fichier / Client", "Lignes", "Statut", "Date", ""],
              history.map((b) => [
                `<strong>${esc(b.filename)}</strong><span class="sub">${esc(b.client)}</span>`,
                `${b.total}<span class="sub">${b.invalid ? b.invalid + " à corriger" : "Aucune erreur"}</span>`,
                operationTag(b.status),
                date(b.created_at),
                `<button class="icon-btn" onclick="openImportPreview('${b.id}')" aria-label="Ouvrir l’import">${icon("chevron")}</button>`,
              ]),
            )
          : empty(
              "Votre premier import commence ici",
              "Les fichiers analysés apparaîtront dans cet historique.",
            )
      }</div>`,
      true,
    );
    const inputEl = $("#import-file"),
      drop = $("#upload-drop");
    const showFile = () => {
      const f = inputEl.files[0];
      $("#upload-file-name").textContent = f
        ? f.name
        : "Glissez votre fichier ici";
      $("#upload-file-meta").textContent = f
        ? (f.size / 1024).toFixed(1) + " Ko · prêt à vérifier"
        : "ou cliquez pour parcourir vos fichiers";
      drop.classList.toggle("selected", !!f);
    };
    inputEl.onchange = showFile;
    drop.ondragover = (e) => {
      e.preventDefault();
      drop.classList.add("dragging");
    };
    drop.ondragleave = () => drop.classList.remove("dragging");
    drop.ondrop = (e) => {
      e.preventDefault();
      drop.classList.remove("dragging");
      if (e.dataTransfer.files.length !== 1) {
        toast("Choisissez un seul fichier à la fois.", true);
        return;
      }
      inputEl.files = e.dataTransfer.files;
      showFile();
    };
    $("#upload-import").onsubmit = async (e) => {
      e.preventDefault();
      const f = e.currentTarget,
        b = f.querySelector("[type=submit]"),
        err = f.querySelector(".form-error");
      b.disabled = true;
      err.style.display = "none";
      b.innerHTML = icon("clock") + "Vérification en cours…";
      try {
        const file = inputEl.files[0];
        if (!file || file.size > 2 * 1024 * 1024)
          throw Error("Choisissez un fichier de moins de 2 Mo.");
        await openImportPreview(
          await uploadApi("/imports/preview", new FormData(f)),
        );
      } catch (error) {
        err.textContent = error.message;
        err.style.display = "block";
      } finally {
        b.disabled = false;
        b.innerHTML = "Vérifier mon fichier " + icon("arrow");
      }
    };
  } catch (e) {
    toast(e.message, true);
  }
}
function operationTag(status) {
  const good = ["Importé", "Validée", "Prêt"].includes(status),
    bad = ["À corriger", "Refusée"].includes(status),
    warning = status === "En attente";
  return `<span class="tag ${good ? "good" : bad ? "bad" : warning ? "warn" : ""}">${esc(status)}</span>`;
}
async function openImportPreview(batch) {
  try {
    importPreview =
      typeof batch === "string" ? await api("/imports/" + batch) : batch;
    importOnlyErrors = !!importPreview.invalid;
    importPage = 1;
    if (importPreview.status === "Importé" && importPreview.result) {
      showImportSuccess(importPreview.result);
      return;
    }
    const b = importPreview;
    modal(
      "Vérifier mon import",
      `${importSteps(2)}<div class="import-title"><div><h3>${esc(b.filename)}</h3><p>${esc(b.client)} · ${b.client_type==='societe_livraison'?'Société de livraison — vos références deviennent les trackings':'Vendeur — trackings ORIENTAL24 automatiques'} · Prévisualisation valable 30 minutes</p></div><button class="btn sm" onclick="openImports()">${icon("upload")}Changer de fichier</button></div><div class="import-metrics"><div><span>Lignes analysées</span><strong>${b.total}</strong></div><div><span>Prêtes à importer</span><strong class="green">${b.valid}</strong></div><div><span>À corriger</span><strong class="${b.invalid ? "error-text" : "muted"}">${b.invalid}</strong></div><div><span>Montant COD valide</span><strong>${money(b.rows.filter((r) => !r.errors.length).reduce((s, r) => s + r.amount, 0))}<small> MAD</small></strong></div></div>${b.invalid ? `<div class="import-alert">${icon("help")}<div><strong>Aucun colis ne sera créé tant qu’il reste une erreur.</strong><p>Corrigez le fichier d’origine, puis importez-le à nouveau. Votre rapport indique les lignes concernées.</p></div><a class="btn sm" href="/api/imports/${b.id}/errors">${icon("download")}Rapport CSV</a></div>` : `<div class="import-ready">${icon("checkcircle")}Toutes les lignes sont valides. Vérifiez les destinataires et les montants avant de confirmer.</div>`}<div class="import-table-shell"><div class="flex between import-table-head"><h4>Détail des lignes</h4>${b.invalid ? `<label class="flex"><input type="checkbox" id="import-only-errors" ${importOnlyErrors ? "checked" : ""} onchange="importOnlyErrors=this.checked;importPage=1;drawImportRows()">Erreurs uniquement</label>` : '<span class="sub">Références uniques vérifiées</span>'}</div><div id="import-rows"></div></div><div class="form-error" id="import-commit-error" role="alert"></div><div class="import-confirm"><span>${icon("lock")}Tarifs et couverture revérifiés à la confirmation.</span><button class="btn primary" id="commit-import" onclick="commitImport()" ${b.invalid ? "disabled" : ""}>${icon("check")}Créer ${b.total} colis</button></div>`,
      true,
    );
    drawImportRows();
  } catch (e) {
    toast(e.message, true);
  }
}
function drawImportRows() {
  if (!$("#import-rows") || !importPreview) return;
  const rows = importPreview.rows.filter(
      (r) => !importOnlyErrors || r.errors.length,
    ),
    pages = Math.max(1, Math.ceil(rows.length / 25));
  importPage = Math.min(importPage, pages);
  $("#import-rows").innerHTML =
    simpleTable(
      ["Ligne / Référence", "Destinataire", "Ville", "COD / Frais", "Contrôle"],
      rows
        .slice((importPage - 1) * 25, importPage * 25)
        .map((r) => [
          `<strong>${r.line}</strong><span class="sub mono">${esc(r.reference || "—")}</span>`,
          `<strong>${esc(r.recipient || "—")}</strong><span class="sub">${esc(r.phone || "—")}</span>`,
          esc(r.city || "—"),
          `${r.amount === null ? "—" : money(r.amount) + " MAD"}<span class="sub">Frais ${r.fee === null ? "—" : money(r.fee) + " MAD"}</span>`,
          r.errors.length
            ? `<div class="row-errors">${r.errors.map((e) => `<span>${esc(e)}</span>`).join("")}</div>`
            : operationTag("Prêt"),
        ]),
    ) +
    `<div class="table-footer"><span>${rows.length} lignes ${importOnlyErrors ? "à corriger" : ""}</span><div class="pagination"><button onclick="importPage=Math.max(1,importPage-1);drawImportRows()" aria-label="Page précédente">‹</button><span>${importPage} / ${pages}</span><button onclick="importPage=Math.min(${pages},importPage+1);drawImportRows()" aria-label="Page suivante">›</button></div></div>`;
}
async function commitImport() {
  const button = $("#commit-import"),
    error = $("#import-commit-error");
  button.disabled = true;
  error.style.display = "none";
  try {
    const result = await api(
      "/imports/" + importPreview.id + "/commit",
      "POST",
      {},
    );
    await refresh();
    shell();
    await renderView();
    showImportSuccess(result);
    toast(
      result.already_imported
        ? "Cet import avait déjà été créé. Aucun doublon ajouté."
        : result.count + " colis créés avec succès",
    );
  } catch (e) {
    error.textContent = e.message;
    error.style.display = "block";
    button.disabled = false;
  }
}
function showImportSuccess(result) {
  const ids = result.parcels.map((p) => p.id);
  modal(
    "Import terminé",
    `${importSteps(3)}<div class="import-success"><span>${icon("checkcircle")}</span><h2>${result.count} colis, prêts pour la suite.</h2><p>Les colis ont été enregistrés. Retrouvez leur suivi dans votre espace.</p></div><div class="import-result-list">${simpleTable(
      ["Commande", "Référence de suivi"],
      result.parcels.map((p) => [
        esc(p.reference),
        `<button class="tracking" onclick="parcelDetail(${p.id})">${esc(p.tracking)}</button>`,
      ]),
    )}</div><div class="form-actions">${ids.length <= 50 ? `<button class="btn" onclick='previewLabels(${JSON.stringify(ids)})'>${icon("print")}Préparer les étiquettes</button>` : ""}<button class="btn primary" onclick="closeModal();filters={q:'',status:'',city:'',from:'',to:''};navigate('parcels')">Voir mes colis ${icon("arrow")}</button></div>${ids.length > 50 ? '<p class="sub">Imprimez les étiquettes par lots de 50 maximum depuis Colis.</p>' : ""}`,
    true,
  );
}

function stockOperationsView(products, requests, movements) {
  productRows = products;
  stockRequestRows = requests;
  stockMovementRows = movements;
  const pending = requests.filter((r) => r.status === "En attente");
  return (
    heading(
      "Stock & produits",
      "De la demande au mouvement physique, rien ne se perd.",
      `<button class="btn" onclick="newStockRequest()">${icon("return")}Demande de stock</button><button class="btn primary" onclick="newProduct()">${icon("plus")}Ajouter un produit</button>`,
    ) +
    `<div class="stats stock-summary">${stat("Références produits", products.length, "", "box", "blue", "Dans votre périmètre")}${stat("Unités disponibles", int(products.reduce((s, p) => s + (p.available ?? p.quantity), 0)), "", "layers", "green", "Stock physique moins réservations")}${stat("Demandes à traiter", pending.length, "", "clock", "", pending.filter((r) => r.kind === "Entrée").length + " entrées · " + pending.filter((r) => r.kind === "Sortie").length + " sorties")}${stat("Mouvements enregistrés", movements.length, "", "chart", "purple", "500 derniers mouvements maximum")}</div><section class="card"><div class="tabs">${[
      ["products", "Produits"],
      ["requests", "Demandes de stock"],
      ["movements", "Historique"],
    ]
      .map(
        ([key, t]) =>
          `<button class="${stockTab === key ? "active" : ""}" onclick="stockTab='${key}';renderView()">${t}${key === "requests" && pending.length ? ` <span class="nav-count stock-badge">${pending.length}</span>` : ""}</button>`,
      )
      .join("")}</div>${
      stockTab === "products"
        ? `<div class="card-head"><h3>Produits en stock</h3><span class="sub">Les demandes de mouvement ne réservent pas ; les commandes de préparation réservent le stock.</span></div>${simpleTable(
            ["Produit / SKU", "Boutique", "Disponible / Réservé", "Créé le", ""],
            products.map((p) => [
              `<div class="recipient"><span class="stock-cube">${icon("box")}</span><div><strong>${esc(p.name)}</strong><span class="sub mono">${esc(p.reference)}</span></div></div>`,
              esc(p.company),
              `<span class="tag ${p.quantity ? "good" : "warn"}">${p.available ?? p.quantity} disponibles</span><span class="sub">${p.reserved ?? 0} réservées · ${p.quantity} physiques</span>`,
              date(p.created_at),
              `<div class="flex"><button class="btn sm" onclick="productDetail(${p.id})">${icon("clock")}Mouvements</button><button class="icon-btn" onclick="newStockRequest(${p.id})" title="Demander une entrée ou sortie">${icon("return")}</button></div>`,
            ]),
          )}`
        : stockTab === "requests"
          ? `<div class="toolbar"><h3 style="font-size:14px">Demandes d’entrée & de sortie</h3><div class="spacer"></div><select aria-label="Filtrer les demandes de stock" onchange="stockFilter=this.value;drawStockRequests()"><option value="all">Tous les statuts</option>${["En attente", "Validée", "Refusée", "Annulée"].map((s) => `<option ${stockFilter === s ? "selected" : ""}>${s}</option>`).join("")}</select></div><div id="stock-requests-table">${stockRequestsTable()}</div>`
          : `<div class="card-head"><h3>Traçabilité des quantités</h3><span class="sub">Du plus récent au plus ancien</span></div>${simpleTable(
              ["Date", "Produit / Boutique", "Quantité", "Motif", "Auteur"],
              movements.map((m) => [
                date(m.created_at),
                `<strong>${esc(m.product)}</strong><span class="sub">${esc(m.company)}</span>`,
                `<span class="tag ${m.delta > 0 ? "good" : "warn"}">${m.delta > 0 ? "+" : ""}${m.delta}</span>`,
                `<span class="wrap-cell">${esc(m.note)}</span>`,
                esc(m.actor),
              ]),
            )}`
    }</section><div class="stock-note">${icon("shield")}Une validation crée un seul mouvement de stock. Un refus ou une annulation ne modifie aucune quantité.</div>`
  );
}
function stockRequestsTable() {
  return simpleTable(
    [
      "Demande",
      "Produit / Client",
      "Opération",
      "Quantité",
      "Statut",
      "Créée le",
      "",
    ],
    stockRequestRows
      .filter((r) => stockFilter === "all" || r.status === stockFilter)
      .map((r) => [
        `<span class="tracking">STK-${String(r.id).padStart(4, "0")}</span>`,
        `<strong>${esc(r.product)}</strong><span class="sub">${esc(r.company || r.client)}</span>`,
        `<span class="flex ${r.kind === "Entrée" ? "green" : "orange"}">${icon(r.kind === "Entrée" ? "download" : "upload")}${r.kind}</span>`,
        `<strong>${r.quantity}</strong>`,
        operationTag(r.status),
        date(r.created_at),
        `<button class="btn sm" onclick="stockRequestDetail(${r.id})">${S.user.role === "admin" && r.status === "En attente" ? "Traiter" : "Détails"} ${icon("chevron")}</button>`,
      ]),
  );
}
function drawStockRequests() {
  if ($("#stock-requests-table"))
    $("#stock-requests-table").innerHTML = stockRequestsTable();
}
function newStockRequest(pid) {
  if (!productRows.length) {
    toast("Ajoutez d’abord un produit.", true);
    return;
  }
  modal(
    "Demande de stock",
    form(
      `${select("product_id", "Produit", [["", "Choisir un produit"], ...productRows.map((p) => [p.id, p.name + " · " + p.reference + (S.user.role === "admin" ? " · " + (p.company || "Client") : "")])], pid || "")}${select(
        "kind",
        "Type de mouvement",
        [
          ["Entrée", "Entrée / alimentation"],
          ["Sortie", "Sortie / retrait"],
        ],
      )}${input("quantity", "Nombre d’unités", 1, "number", true, 'min="1" max="100000" step="1"')}<div class="form-hint stock-available" id="stock-available">Sélectionnez un produit pour voir son stock.</div>${textarea("reason", "Motif et instructions", "", true)}<div class="full form-hint orange">La demande ne modifie ni ne réserve le stock. L’administration valide l’opération après contrôle physique ; le stock disponible est revérifié à cet instant.</div>`,
      "Envoyer la demande",
    ),
  );
  const update = () => {
    const p = productRows.find(
      (p) => String(p.id) === $("#f-product_id").value,
    );
    $("#stock-available").innerHTML = p
      ? `Stock disponible<strong>${p.quantity} unités</strong>`
      : "Sélectionnez un produit pour voir son stock.";
  };
  $("#f-product_id").onchange = update;
  update();
  bindForm(async (d) => {
    await api("/stock/requests", "POST", d);
    stockTab = "requests";
    stockFilter = "all";
    await saved("Demande de stock envoyée");
  });
}
function stockRequestDetail(id) {
  const r = stockRequestRows.find((r) => r.id === id);
  if (!r) return;
  modal(
    "STK-" + String(id).padStart(4, "0"),
    `<div class="flex between" style="margin-bottom:22px"><div><h3>${esc(r.product)}</h3><span class="sub">${esc(r.sku)} · ${esc(r.company || r.client)}</span></div>${operationTag(r.status)}</div><div class="stock-request-summary"><span class="stat-icon ${r.kind === "Entrée" ? "green" : ""}">${icon(r.kind === "Entrée" ? "download" : "upload")}</span><div><span>${r.kind === "Entrée" ? "Entrée en stock" : "Sortie de stock"}</span><strong>${r.quantity} unités</strong></div><div class="right"><span>Disponible actuellement</span><strong>${r.available} unités</strong></div></div><div class="detail-info"><label>Motif / instructions</label><p style="white-space:pre-wrap;font-size:12px">${esc(r.reason)}</p></div><div class="timeline"><div class="timeline-item"><b>Demande créée</b><p>${esc(r.creator)}</p><small>${date(r.created_at)}</small></div>${r.processed_at ? `<div class="timeline-item"><b>${esc(r.status)}</b><p>${esc(r.processor)}${r.admin_note ? " · " + esc(r.admin_note) : ""}</p><small>${date(r.processed_at)}${r.movement_id ? " · Mouvement #" + r.movement_id : ""}</small></div>` : ""}</div>${
      r.status === "En attente"
        ? S.user.role === "admin"
          ? `<form id="stock-decision-form"><div class="form-error" role="alert"></div>${select(
              "status",
              "Décision",
              [
                ["Validée", "Valider le mouvement physique"],
                ["Refusée", "Refuser la demande"],
              ],
            )}${textarea("admin_note", "Commentaire (obligatoire en cas de refus)")}<label class="decision-check"><input type="checkbox" required>J’ai vérifié l’opération et sa quantité avant traitement.</label><div class="form-actions"><button type="submit" class="btn primary">${icon("check")}Confirmer la décision</button></div></form>`
          : `<div class="form-actions"><button class="btn danger" onclick="cancelStockRequest(${r.id})">Annuler ma demande</button></div>`
        : ""
    }`,
  );
  if (S.user.role === "admin" && r.status === "En attente")
    bindForm(async (d) => {
      await api("/stock/requests/" + id, "PATCH", d);
      await saved(
        d.status === "Validée"
          ? "Demande validée et stock mis à jour"
          : "Demande refusée sans modification du stock",
      );
    }, "stock-decision-form");
}
function cancelStockRequest(id) {
  modal(
    "Annuler ma demande ?",
    form(
      '<div class="full form-hint">La demande sera clôturée sans modifier le stock. Vous pourrez en créer une nouvelle si nécessaire.</div>',
      "Annuler la demande",
    ),
  );
  bindForm(async () => {
    await api("/stock/requests/" + id, "PATCH", { status: "Annulée" });
    await saved("Demande annulée");
  });
}

function labelMarkup(p) {
  return `<article class="shipping-label"><header><img src="/static/wordmark.png" alt="ORIENTAL24"><span>LIVRAISON À DOMICILE</span></header><div class="label-destination"><div><span>DESTINATION</span><h2>${esc(p.city)}</h2><p>${esc(p.tracking)}</p></div><img src="${p.qr}" alt="QR de suivi ${esc(p.tracking)}"></div><div class="label-address"><span>DESTINATAIRE</span><h3>${esc(p.recipient)}</h3><strong>${esc(p.phone)}</strong><p>${esc(p.address)}</p></div><div class="label-cod"><span>MONTANT À COLLECTER</span><strong>${money(p.amount)} <small>MAD</small></strong></div><div class="label-sender"><span>EXPÉDITEUR</span><b>${esc(p.company || p.client)}</b><p>${esc(p.product || "Colis")}</p>${p.note ? `<p class="label-note">${esc(p.note)}</p>` : ""}</div><div class="label-barcode"><img src="${p.barcode}" alt="Code 128 ${esc(p.tracking)}"></div><footer><span>${date(p.created_at)}</span><span>QR & Code 128 · Référence de suivi</span></footer></article>`;
}
async function previewLabels(ids) {
  if (!ids.length || ids.length > 50) {
    toast("Sélectionnez entre 1 et 50 colis.", true);
    return;
  }
  try {
    const records = await api("/labels", "POST", { ids });
    labelPreview = {
      records,
      index: 0,
      format: records.some(labelIsLong) ? "A4" : "A6",
    };
    renderLabelPreview();
  } catch (e) {
    toast(e.message, true);
  }
}
function renderLabelPreview() {
  const p = labelPreview.records[labelPreview.index],
    n = labelPreview.records.length;
  modal(
    "Étiquettes de livraison",
    `<div class="label-preview-layout"><div class="label-preview-paper">${labelMarkup(p)}</div><aside class="label-options"><span class="eyebrow orange">Prêtes à scanner</span><h3>Une étiquette.<br>Tout le nécessaire.</h3><p>QR code et code-barres Code 128 contiennent la référence du colis. La consultation de ses détails nécessite une connexion autorisée.</p><label for="label-format">Format d’impression</label><select id="label-format" onchange="labelPreview.format=this.value"><option value="A6" ${labelPreview.format === "A6" ? "selected" : ""}>A6 · 105 × 148 mm</option><option value="thermal" ${labelPreview.format === "thermal" ? "selected" : ""}>Thermique · 100 × 150 mm</option><option value="A4" ${labelPreview.format === "A4" ? "selected" : ""}>A4 · adresses ou notes longues</option></select><div class="label-pager"><button class="icon-btn" onclick="labelPreview.index=Math.max(0,labelPreview.index-1);renderLabelPreview()" ${labelPreview.index === 0 ? "disabled" : ""} aria-label="Étiquette précédente">${icon("back")}</button><span>${labelPreview.index + 1} / ${n}</span><button class="icon-btn" onclick="labelPreview.index=Math.min(${n - 1},labelPreview.index+1);renderLabelPreview()" ${labelPreview.index === n - 1 ? "disabled" : ""} aria-label="Étiquette suivante">${icon("arrow")}</button></div><button class="btn primary" id="print-labels-button" onclick="printPreparedLabels()">${icon("print")}Imprimer ${n > 1 ? n + " étiquettes" : "l’étiquette"}</button><div class="form-hint">Pour un PDF, choisissez « Enregistrer au format PDF ». Imprimez à 100 %, sans en-têtes ni pieds de page du navigateur.</div><small>Si l’impression est bloquée dans l’aperçu, ouvrez la plateforme dans un nouvel onglet.</small></aside></div>`,
    true,
  );
}
function labelIsLong(p) {
  return (
    [
      "recipient",
      "address",
      "city",
      "product",
      "note",
      "company",
      "client",
    ].reduce((sum, k) => sum + String(p[k] || "").length, 0) > 450
  );
}
async function printPreparedLabels() {
  if (labelPreview.format !== "A4" && labelPreview.records.some(labelIsLong)) {
    toast(
      "Certains textes sont longs : choisissez le format A4 pour ne pas couper les informations.",
      true,
    );
    return;
  }
  const b = $("#print-labels-button");
  b.disabled = true;
  try {
    const dim =
      labelPreview.format === "thermal"
        ? "100mm 150mm"
        : labelPreview.format === "A4"
          ? "210mm 297mm"
          : "105mm 148mm";
    await doPrint(
      `<style>@page{size:${dim};margin:4mm}#print-root .label-sheet{border:0;padding:0;margin:0;break-after:page;page-break-after:always}#print-root .label-sheet:last-child{break-after:auto;page-break-after:auto}#print-root{padding:0}${labelPreview.format === "A4" ? "#print-root .shipping-label{max-width:180mm;margin:auto}" : ""}</style>` +
        labelPreview.records
          .map(
            (p) => `<section class="label-sheet">${labelMarkup(p)}</section>`,
          )
          .join(""),
    );
  } catch (e) {
    toast("Impossible de préparer l’impression : " + e.message, true);
  } finally {
    b.disabled = false;
  }
}

async function openScanner() {
  modal(
    "Retrouver un colis",
    `<div class="scan-stage" id="scan-stage"><div class="scan-placeholder" id="scan-placeholder">${icon("scan")}<h3>Un scan. Le bon colis.</h3><p>Scannez le QR ou le code-barres du colis, ORIENTAL24 ou société partenaire.</p></div><video id="scan-video" playsinline muted hidden></video><div class="scan-frame" id="scan-frame" hidden></div></div><div class="scan-camera-row"><button class="btn" id="camera-button" onclick="startScannerCamera()">${icon("scan")}Activer la caméra</button><span id="camera-status">Caméra facultative</span></div><form id="scan-form"><div class="form-error" role="alert"></div>${input("tracking", "Référence du colis", "", "text", true, 'placeholder="O24-… ou tracking partenaire" autocomplete="off" maxlength="80"')}<p class="sub">Saisie manuelle ou lecteur USB/Bluetooth : scannez puis appuyez sur Entrée.</p><button type="submit" class="btn primary" style="margin-top:18px;width:100%">Retrouver le colis ${icon("arrow")}</button></form><div class="scan-access">${icon("lock")}Seuls les colis de votre périmètre sont accessibles. Le scan ne modifie pas le statut.</div>`,
  );
  bindForm(async (d) => {
    const p = await api("/scan", "POST", d);
    await refresh();
    await parcelDetail(p.id);
  }, "scan-form");
}
async function startScannerCamera() {
  const button = $("#camera-button"),
    status = $("#camera-status");
  if (!button) return;
  if (!("BarcodeDetector" in window) || !navigator.mediaDevices?.getUserMedia) {
    status.textContent =
      "Lecture caméra indisponible ici. Utilisez la saisie ou un lecteur externe.";
    return;
  }
  button.disabled = true;
  status.textContent = "Autorisez l’accès à la caméra…";
  let active = true,
    stream = null,
    timer = null;
  const cleanup = () => {
    active = false;
    clearTimeout(timer);
    stream?.getTracks().forEach((t) => t.stop());
    const v = $("#scan-video");
    if (v) v.srcObject = null;
  };
  modalCleanup = cleanup;
  try {
    const supported = await BarcodeDetector.getSupportedFormats();
    const formats = ["qr_code", "code_128"].filter((x) =>
      supported.includes(x),
    );
    if (!formats.length) throw Error("Formats non pris en charge");
    const detector = new BarcodeDetector({ formats });
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } },
      audio: false,
    });
    if (!active) {
      stream.getTracks().forEach((t) => t.stop());
      return;
    }
    const video = $("#scan-video");
    video.srcObject = stream;
    video.hidden = false;
    $("#scan-placeholder").hidden = true;
    $("#scan-frame").hidden = false;
    await video.play();
    if (!active) return;
    status.textContent = "Placez le code dans le cadre.";
    button.innerHTML = icon("close") + "Arrêter la caméra";
    button.disabled = false;
    button.onclick = () => {
      cleanup();
      openScanner();
    };
    let last = "";
    const loop = async () => {
      if (!active) return;
      try {
        const codes = await detector.detect(video);
        if (!active) return;
        const value = codes.find((c) => c.rawValue)?.rawValue?.trim();
        if (value && value !== last) {
          last = value;
          if (!/^[A-Za-z0-9][A-Za-z0-9._/\-]{0,79}$/.test(value)) {
            status.textContent = "Format de tracking non reconnu.";
          } else {
            const result = await api("/scan", "POST", { tracking: value });
            if (!active) return;
            cleanup();
            await refresh();
            await parcelDetail(result.id);
            return;
          }
        }
      } catch (e) {
        if (active) status.textContent = e.message;
      }
      if (active) timer = setTimeout(loop, 300);
    };
    loop();
  } catch (e) {
    cleanup();
    if ($("#camera-status")) {
      $("#camera-status").textContent =
        "Caméra indisponible ou refusée. Ouvrez dans un nouvel onglet, ou saisissez le code.";
      button.disabled = false;
    }
  }
}

