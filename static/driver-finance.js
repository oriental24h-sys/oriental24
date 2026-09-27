/* ORIENTAL24 1.2 — driver statements, configurable commissions and manual cash ledger. */
let financeTab = "statements",
  financeData = null,
  financeDrivers = [],
  financeDetail = null,
  financeDetailTab = "parcels",
  financePreview = null;
let financeFilters = { driver: "", status: "", query: "" },
  financePage = 1,
  rateRowSerial = 0;
const centMoney = (v) => money(Number(v || 0) / 100);
const centInput = (v) =>
  v === undefined || v === null ? "" : (Number(v) / 100).toFixed(2);
const financeMode = (m) =>
  m === "net" ? "COD net de commission" : "COD intégral + commission séparée";
const statementRef = (id) => "DRV-" + String(id).padStart(6, "0");
const financeStatus = (s) =>
  `<span class="tag ${s === "Soldé" ? "good" : s === "Partiel" ? "blue" : s === "Annulé" ? "bad" : "warn"}">${esc(s)}</span>`;
function financeDay() {
  return new Date().toLocaleDateString("en-CA", {
    timeZone: "Africa/Casablanca",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}
function financePeriod(p) {
  return p.period_from || p.period_to
    ? `${p.period_from ? date(p.period_from) : "Début"} → ${p.period_to ? date(p.period_to) : "Aujourd’hui"}`
    : "Toutes les périodes";
}
function financeKey() {
  return [...crypto.getRandomValues(new Uint8Array(16))]
    .map((x) => x.toString(16).padStart(2, "0"))
    .join("");
}
async function openDriverFinance(tab = "statements") {
  financeTab = tab;
  await navigate("driver-finance");
}
function driverFinanceView(data, drivers) {
  financeData = data;
  financeDrivers = drivers;
  if (S.user.role !== "admin" && financeTab === "rates")
    financeTab = "statements";
  const admin = S.user.role === "admin",
    sum = data.summary,
    unconfigured = drivers.filter((d) => !d.terms && d.active);
  return (
    heading(
      admin ? "Caisse & commissions" : "Ma caisse & mes commissions",
      admin
        ? "Du colis livré au règlement, chaque dirham a sa trace."
        : "Vos relevés, vos remises COD et vos commissions au même endroit.",
      `<a class="btn export-btn" href="/api/driver-finance/export">${icon("download")}Exporter les relevés</a>${admin ? `<button class="btn" onclick="editDriverInvoiceProfile()">${icon("file")}Coordonnées des factures</button><button class="btn primary" onclick="newDriverStatement()">${icon("plus")}Nouveau relevé</button>` : ""}`,
    ) +
    `<div class="finance-context"><span>${icon("shield")}Suivi de caisse interne</span><p>Les écritures constatent des paiements déjà réalisés. Aucun virement n’est déclenché.</p><span class="finance-currency">MAD · Montants au centime</span></div><section class="stats finance-stats">${stat("COD des relevés", centMoney(sum.cod_cents), "MAD", "wallet", "blue", "Relevés actifs, toutes périodes")}${stat("Commissions constatées", centMoney(sum.commission_cents), "MAD", "truck", "purple", "Tarifs figés à l’émission")}${stat("COD restant à remettre", centMoney(sum.cash_remaining_cents), "MAD", "download", "", "Livreur → ORIENTAL24")}${stat("Commissions restant à payer", centMoney(sum.commission_remaining_cents), "MAD", "upload", "green", "ORIENTAL24 → livreur")}</section>${admin && unconfigured.length ? `<div class="finance-setup-alert"><span class="stat-icon">${icon("settings")}</span><div><strong>${unconfigured.length} livreur${unconfigured.length > 1 ? "s" : ""} sans barème</strong><p>Aucune commission n’est inventée. Configurez les montants avant d’émettre un relevé.</p></div><button class="btn sm" onclick="financeTab='rates';renderView()">Configurer ${icon("arrow")}</button></div>` : ""}<section class="card"><div class="tabs">${[["statements", "Relevés livreurs"], ["transactions", "Journal des règlements"], ["days", "Fin de journée"], ...(admin ? [["bank", "Rapprochement CSV"], ["rates", "Barèmes & méthodes"]] : [])].map(([key, title]) => `<button class="${financeTab === key ? "active" : ""}" onclick="financeTab='${key}';renderView()">${title}${key === "statements" ? ` <span class="finance-count">${data.statements.length}</span>` : ""}</button>`).join("")}</div>${financeTab === "statements" ? `<div class="toolbar"><div class="search-field">${icon("search")}<input id="finance-search" value="${esc(financeFilters.query)}" placeholder="Référence, livreur…" oninput="financeFilters.query=this.value;financePage=1;drawFinanceStatements()"></div>${admin ? `<select aria-label="Filtrer les relevés par livreur" onchange="financeFilters.driver=this.value;financePage=1;drawFinanceStatements()"><option value="">Tous les livreurs</option>${drivers.map((d) => `<option value="${d.id}" ${String(d.id) === financeFilters.driver ? "selected" : ""}>${esc(d.name)}</option>`).join("")}</select>` : ""}<select aria-label="Filtrer les relevés par statut" onchange="financeFilters.status=this.value;financePage=1;drawFinanceStatements()"><option value="">Tous les statuts</option>${["À régler", "Partiel", "Soldé", "Annulé"].map((s) => `<option ${s === financeFilters.status ? "selected" : ""}>${s}</option>`).join("")}</select><div class="spacer"></div><button class="icon-btn" onclick="reloadView()" title="Actualiser la caisse">${icon("refresh")}</button></div><div id="finance-statements">${financeStatementsTable()}</div>` : financeTab === "transactions" ? `<div class="card-head"><div><h3>Chaque mouvement, sans effacer l’historique.</h3><p>500 dernières écritures · Les annulations restent visibles.</p></div>${icon("file")}</div>${financeTransactionTable(data.transactions, true)}` : financeTab === "bank" ? bankShell() : financeTab === "days" ? financeDaysShell() : financeRatesView()}</section><div class="finance-bottom-note">${icon("lock")}Les relevés clients et les relevés livreurs sont indépendants. Les totaux excluent les relevés annulés.</div>`
  );
}
function financeStatementsTable() {
  const query = financeFilters.query.toLowerCase();
  const rows = financeData.statements.filter(
    (s) =>
      (!financeFilters.driver ||
        String(s.driver_id) === financeFilters.driver) &&
      (!financeFilters.status || s.status === financeFilters.status) &&
      (!query ||
        [s.reference, s.driver_name].some((x) =>
          x.toLowerCase().includes(query),
        )),
  );
  if (!rows.length)
    return empty(
      financeData.statements.length
        ? "Aucun relevé correspondant"
        : "Une caisse claire commence ici",
      S.user.role === "admin"
        ? "Configurez un barème, vérifiez les colis clôturés, puis émettez votre premier relevé."
        : "Vos relevés apparaîtront ici après leur émission par l’administration.",
      S.user.role === "admin"
        ? `<button class="btn primary" onclick="newDriverStatement()">${icon("plus")}Créer un relevé</button>`
        : "",
    );
  const pages = Math.max(1, Math.ceil(rows.length / 10));
  financePage = Math.min(financePage, pages);
  const current = rows.slice((financePage - 1) * 10, financePage * 10);
  return `<div class="finance-desktop">${simpleTable(
    [
      "Relevé / Livreur",
      "COD déclaré",
      "Commission",
      "COD à remettre",
      "Commission à payer",
      "État",
      "",
    ],
    current.map((s) => [
      `<button class="tracking" onclick="openDriverStatement(${s.id})">${esc(s.reference)}</button><span class="sub">${esc(s.driver_name)} · ${s.parcel_count} colis</span><span class="sub">${date(s.created_at)} · ${s.mode === "net" ? "Net" : "Intégral"}</span>`,
      `${centMoney(s.cod_cents)} <small>MAD</small>`,
      `${centMoney(s.commission_cents)} <small>MAD</small>`,
      `<strong class="${s.cash_remaining_cents ? "orange" : "green"}">${centMoney(s.cash_remaining_cents)}</strong> <small>MAD</small>`,
      `<strong>${centMoney(s.commission_remaining_cents)}</strong> <small>MAD</small>`,
      financeStatus(s.status),
      `<button class="icon-btn" onclick="openDriverStatement(${s.id})" aria-label="Ouvrir ${s.reference}">${icon("chevron")}</button>`,
    ]),
  )}</div><div class="finance-mobile">${current.map((s) => `<article class="finance-mobile-statement"><div class="flex between"><button class="tracking" onclick="openDriverStatement(${s.id})">${esc(s.reference)}</button>${financeStatus(s.status)}</div><h3>${esc(s.driver_name)}</h3><p>${s.parcel_count} colis · ${date(s.created_at)}</p><div class="finance-mobile-balances"><div><span>COD à remettre</span><b>${centMoney(s.cash_remaining_cents)} <small>MAD</small></b></div><div><span>Commission à payer</span><b>${centMoney(s.commission_remaining_cents)} <small>MAD</small></b></div></div><button class="btn" onclick="openDriverStatement(${s.id})">Consulter le relevé ${icon("arrow")}</button></article>`).join("")}</div><div class="table-footer"><span>${rows.length} relevés · Soldes restants après écritures valides</span><div class="pagination"><button onclick="financePage=Math.max(1,financePage-1);drawFinanceStatements()" aria-label="Page précédente">‹</button><span>${financePage} / ${pages}</span><button onclick="financePage=Math.min(${pages},financePage+1);drawFinanceStatements()" aria-label="Page suivante">›</button></div></div>`;
}
function drawFinanceStatements() {
  if ($("#finance-statements"))
    $("#finance-statements").innerHTML = financeStatementsTable();
}
function financeRatesView() {
  return `<div class="finance-rates-intro"><div><span class="eyebrow orange">Vos règles, pas des montants par défaut</span><h3>Le bon barème pour chaque livreur.</h3><p>Définissez les commissions par statut, ajoutez des exceptions par ville, puis choisissez comment le COD est remis. Ces frais sont distincts des tarifs facturés au client.</p></div><span class="finance-settings-icon">${icon("settings")}</span></div><div class="finance-driver-grid">${
    financeDrivers
      .map(
        (d) =>
          `<article class="finance-driver-card"><div class="flex between"><div class="flex"><span class="avatar orange">${initials(d.name)}</span><div><h3>${esc(d.name)}</h3><span class="sub">${esc(d.phone)}</span></div></div><span class="tag ${d.terms ? "good" : "warn"}">${d.terms ? "Configuré" : "À configurer"}</span></div>${
            d.terms
              ? `<div class="finance-mode-chip">${icon(d.terms.mode === "net" ? "return" : "wallet")}${financeMode(d.terms.mode)}</div><div class="finance-rate-values">${[
                  ["Livré", "delivered_cents"],
                  ["Retourné", "returned_cents"],
                  ["Refusé", "refused_cents"],
                ]
                  .map(
                    ([label, key]) =>
                      `<div><span>${label}</span><strong>${centMoney(d.terms[key])}<small> MAD</small></strong></div>`,
                  )
                  .join(
                    "",
                  )}</div><div class="flex between finance-rate-meta"><span>${d.terms.overrides.length} exception${d.terms.overrides.length !== 1 ? "s" : ""} par ville</span><span>Version ${d.terms.revision}</span></div>`
              : `<div class="finance-unconfigured">${icon("help")}Aucun montant ni méthode enregistrés. La génération d’un relevé est bloquée pour ce livreur.</div>`
          }<div class="flex between"><button class="btn ${d.terms ? "" : "primary"} sm" onclick="editDriverTerms(${d.id})">${icon("edit")}${d.terms ? "Modifier le barème" : "Configurer le barème"}</button>${d.terms ? `<button class="section-link" onclick="showDriverTermsHistory(${d.id})">Historique ${icon("clock")}</button>` : ""}</div></article>`,
      )
      .join("") ||
    empty(
      "Aucun livreur",
      "Créez d’abord un compte livreur depuis la rubrique Livreurs.",
    )
  }</div><div class="finance-rule-note">${icon("shield")}Une modification s’applique aux prochains relevés, y compris pour les colis anciens non rapprochés. Les relevés déjà émis ne changent jamais.</div>`;
}
async function editDriverTerms(id) {
  try {
    financeDrivers = await api("/driver-finance/terms");
    const driver = financeDrivers.find((d) => d.id === id),
      terms = driver?.terms;
    if (!driver) throw Error("Livreur introuvable.");
    rateRowSerial = 0;
    modal(
      "Barème · " + driver.name,
      `<form id="driver-terms-form"><div class="form-error" role="alert"></div><div class="finance-mode-explainer"><h3>Comment le livreur remet-il le COD ?</h3><div><p><b>Net :</b> il garde la commission autorisée et remet le reste. Si la commission dépasse le COD, la différence reste à lui payer.</p><p><b>Intégral :</b> il remet tout le COD ; sa commission est réglée séparément.</p></div></div>${select(
        "mode",
        "Méthode de règlement",
        [
          ["", "Choisir une méthode"],
          ["net", "COD net de commission"],
          ["gross", "COD intégral + commission séparée"],
        ],
        terms?.mode || "",
      )}<div class="finance-form-section"><h3>Commissions par défaut <small>MAD / colis</small></h3><p>Saisissez 0 explicitement si un statut n’est pas rémunéré. Une seule commission est retenue par colis, selon son statut au moment de l’émission.</p><div class="finance-three-fields">${input("delivered", "Colis livré", centInput(terms?.delivered_cents), "number", true, 'min="0" max="10000" step="0.01"')}${input("returned", "Colis retourné", centInput(terms?.returned_cents), "number", true, 'min="0" max="10000" step="0.01"')}${input("refused", "Colis refusé", centInput(terms?.refused_cents), "number", true, 'min="0" max="10000" step="0.01"')}</div></div><div class="finance-form-section"><div class="flex between"><h3>Exceptions par ville</h3><button type="button" class="btn sm" onclick="addCityCommissionRow()">${icon("plus")}Ajouter une ville</button></div><p>Sans exception, le barème par défaut du livreur s’applique. Les villes désactivées restent configurables pour leurs anciens colis.</p><div id="city-commission-rows"></div></div><div class="form-hint orange">Ces montants sont propres au livreur : ils ne modifient ni le COD du destinataire ni les frais du client. Les changements sont historisés.</div><div class="form-actions"><button type="button" class="btn" onclick="closeModal()">Annuler</button><button type="submit" class="btn primary">${icon("check")}Enregistrer le barème</button></div></form>`,
      true,
    );
    (terms?.overrides || []).forEach((r) => addCityCommissionRow(r));
    bindForm(async (data) => {
      const overrides = [
        ...document.querySelectorAll(".city-commission-row"),
      ].map((row) => ({
        city_id: Number(row.querySelector("[data-rate=city]").value),
        delivered: row.querySelector("[data-rate=delivered]").value,
        returned: row.querySelector("[data-rate=returned]").value,
        refused: row.querySelector("[data-rate=refused]").value,
      }));
      await api409(
        (f)=>api("/driver-finance/terms/" + id, "PUT", {
          mode: data.mode,
          delivered: data.delivered,
          returned: data.returned,
          refused: data.refused,
          revision: f? f.revision : terms?.revision || 0,
          overrides,
        }),
        async()=>({revision:(await api("/driver-finance/terms")).find(x=>x.id===id)?.terms?.revision ?? 0}),
      );
      financeTab = "rates";
      if (view !== "driver-finance") {
        await refresh();
        closeModal();
        await openDriverFinance("rates");
        toast("Barème enregistré");
      } else await saved("Barème enregistré · prochains relevés uniquement");
    }, "driver-terms-form");
  } catch (e) {
    toast(e.message, true);
  }
}
function addCityCommissionRow(rate = null) {
  const serial = ++rateRowSerial;
  $("#city-commission-rows").insertAdjacentHTML(
    "beforeend",
    `<div class="city-commission-row"><div><label for="rate-city-${serial}">Ville</label><select id="rate-city-${serial}" data-rate="city" required><option value="">Choisir</option>${S.cities.map((c) => `<option value="${c.id}" ${c.id === rate?.city_id ? "selected" : ""}>${esc(c.name)}${!c.delivery ? " · inactive" : ""}</option>`).join("")}</select></div>${[
      ["delivered", "Livré"],
      ["returned", "Retourné"],
      ["refused", "Refusé"],
    ]
      .map(
        ([key, label]) =>
          `<div><label for="rate-${key}-${serial}">${label} (MAD)</label><input id="rate-${key}-${serial}" data-rate="${key}" type="number" min="0" max="10000" step="0.01" required value="${centInput(rate?.[key + "_cents"])}"></div>`,
      )
      .join(
        "",
      )}<button type="button" class="icon-btn" onclick="this.closest('.city-commission-row').remove()" aria-label="Retirer cette exception">${icon("close")}</button></div>`,
  );
}
async function showDriverTermsHistory(id) {
  try {
    const rows = await api("/driver-finance/terms/" + id + "/history");
    modal(
      "Historique du barème",
      `<div class="form-hint">Chaque enregistrement crée une version, sans modifier les relevés émis.</div><div class="timeline finance-rate-history">${
        rows
          .map((r) => {
            const t = r.details.after;
            return `<div class="timeline-item"><b>Version ${t.revision} · ${financeMode(t.mode)}</b><p>Livré : ${centMoney(t.delivered_cents)} MAD · Retourné : ${centMoney(t.returned_cents)} MAD · Refusé : ${centMoney(t.refused_cents)} MAD</p>${
              t.overrides.length
                ? `<details><summary>${t.overrides.length} exception(s) par ville</summary>${simpleTable(
                    ["Ville", "Livré", "Retourné", "Refusé"],
                    t.overrides.map((o) => [
                      esc(o.city),
                      centMoney(o.delivered_cents),
                      centMoney(o.returned_cents),
                      centMoney(o.refused_cents),
                    ]),
                  )}</details>`
                : ""
            }<small>${esc(r.actor_name)} · ${date(r.created_at)}</small></div>`;
          })
          .join("") ||
        empty(
          "Aucun barème enregistré",
          "Le premier enregistrement sera historisé.",
        )
      }</div>`,
      true,
    );
  } catch (e) {
    toast(e.message, true);
  }
}
async function newDriverStatement() {
  if (S?.user?.role !== 'admin') return;
  const owner=S.user.id;
  modal('Préparer un relevé livreur','<p class="sub">Chargement des livreurs…</p>');
  const node=$('#modal-root .modal'),current=()=>node.isConnected&&S?.user?.id===owner;
  try {
    const drivers=await api('/driver-finance/terms');
    if(!current())return;
    financeDrivers=drivers;
    node.querySelector('.modal-body').innerHTML=form(
      `${select("driver_id", "Livreur", [["", "Choisir un livreur"], ...drivers.map((d) => [d.id, d.name + (!d.active ? " · compte inactif, règlement historique" : "") + (d.terms ? "" : " · barème à configurer")])])}<div class="form-hint">Seuls les colis livrés, retournés ou refusés, assignés à ce livreur et non déjà rapprochés, seront proposés.</div>${input("period_from", "Du", "", "date", false)}${input("period_to", "Au", "", "date", false)}<div class="full form-hint">La période filtre la date de dernière mise à jour enregistrée du colis. Laissez vide pour tout inclure. Maximum 500 colis par relevé.</div><div class="full finance-preview-reassure">${icon("eye")}Rien n’est émis à cette étape : vous vérifiez les montants avant confirmation.</div>`,
      "Vérifier les montants",
    );
    bindForm(async (d) => {
      const preview=await api('/driver-finance/preview','POST',d);
      if(!current())return;
      financePreview=preview;renderDriverPreview();
    });
  } catch(e) {if(current())node.querySelector('.modal-body').innerHTML=`<p class="form-hint">${esc(e.message)}</p>`;}
}
function financeAmounts(p) {
  return `<div class="finance-calculation"><div><span>COD des colis livrés</span><strong>${centMoney(p.cod_cents)} <small>MAD</small></strong></div><div><span>Commissions du livreur</span><strong>${centMoney(p.commission_cents)} <small>MAD</small></strong></div><div><span>Retenue autorisée sur le COD</span><strong>${centMoney(p.retained_cents)} <small>MAD</small></strong></div><div class="total"><span>COD à remettre à ORIENTAL24</span><strong>${centMoney(p.cash_due_cents)} <small>MAD</small></strong></div><div class="total commission"><span>Commission à payer séparément</span><strong>${centMoney(p.commission_due_cents)} <small>MAD</small></strong></div></div>`;
}
function financeLinesTable(rows) {
  return simpleTable(
    [
      "Colis",
      "Ville / Mise à jour",
      "Statut",
      "COD déclaré",
      "Commission",
      "Barème",
    ],
    rows.map((p) => [
      `<span class="tracking">${esc(p.tracking)}</span>`,
      `${esc(p.city)}<span class="sub">${date(p.closed_at)}</span>`,
      tag(p.status),
      `${centMoney(p.cod_cents)} MAD`,
      `<strong>${centMoney(p.commission_cents)} MAD</strong>`,
      esc(p.rate_source),
    ]),
  );
}
function renderDriverPreview() {
  const p = financePreview;
  modal(
    "Vérifier le relevé livreur",
    `<div class="finance-review-heading"><div><span class="eyebrow orange">Prévisualisation · Aucun règlement effectué</span><h3>${esc(p.driver_name)}</h3><p>${financePeriod(p)} · ${p.parcel_count} colis · Barème v${p.revision}</p></div><span class="finance-mode-chip">${icon("wallet")}${p.mode === "net" ? "Remise nette" : "Remise intégrale"}</span></div>${financeAmounts(p)}<div class="finance-review-message">${icon("lock")}La confirmation fige les commissions et verrouille les colis. Les données seront revérifiées pour éviter les doublons et les tarifs obsolètes.</div><div class="finance-lines">${financeLinesTable(p.lines)}</div><div class="form-error" id="finance-preview-error" role="alert"></div><div class="finance-confirm-row"><span>Valable 30 minutes · Relevé interne, hors facture fiscale.</span><button class="btn primary" id="finance-confirm" onclick="confirmDriverStatement()">${icon("check")}Émettre le relevé</button></div>`,
    true,
  );
}
async function confirmDriverStatement() {
  const b = $("#finance-confirm"),
    err = $("#finance-preview-error");
  b.disabled = true;
  err.style.display = "none";
  try {
    const result = await api(
      "/driver-finance/preview/" + financePreview.token + "/confirm",
      "POST",
      {},
    );
    await refresh();
    financeTab = "statements";
    if (view === "invoices") billingReset("livreur");
    await renderView();
    await openDriverStatement(result.statement_id);
    toast(
      result.already_created
        ? "Relevé déjà émis : aucun doublon créé."
        : "Relevé émis. Les montants sont figés.",
    );
  } catch (e) {
    err.textContent = e.message;
    err.style.display = "block";
    b.disabled = false;
  }
}
async function openDriverStatement(id, tab = "parcels") {
  try {
    financeDetail = await api("/driver-finance/statements/" + id);
    financeDetailTab = tab;
    renderDriverStatement();
  } catch (e) {
    toast(e.message, true);
  }
}
function financeBalanceCard(s, kind) {
  const cash = kind === "cash",
    due = s[cash ? "cash_due_cents" : "commission_due_cents"],
    paid = s[cash ? "cash_received_cents" : "commission_paid_cents"],
    remaining = s[cash ? "cash_remaining_cents" : "commission_remaining_cents"];
  return `<div class="finance-balance-card ${cash ? "cash" : "commission"}"><div class="flex between"><span>${cash ? "COD à remettre" : "Commission à payer"}</span>${icon(cash ? "download" : "upload")}</div><strong>${centMoney(remaining)} <small>MAD restants</small></strong><div class="bar"><span style="width:${s.cancelled_at ? 0 : due ? Math.min(100, Math.round((paid / due) * 100)) : 100}%"></span></div><div class="flex between"><small>${cash ? "Reçu" : "Payé"} : ${centMoney(paid)} MAD</small><small>Prévu : ${centMoney(due)} MAD</small></div>${S.user.role === "admin" && remaining > 0 && !s.cancelled_at ? `<button class="btn sm" onclick="recordDriverTransaction('${kind}')">${icon("plus")}${cash ? "Enregistrer une remise" : "Enregistrer un paiement"}</button>` : `<div class="finance-balance-caption">${s.cancelled_at ? "Relevé annulé" : remaining ? "Enregistrement par l’administration uniquement" : cash ? "Aucun COD restant à remettre" : "Aucune commission restant à payer"}</div>`}</div>`;
}
function renderDriverStatement() {
  const { statement: s, lines, transactions, audit } = financeDetail;
  const admin = S.user.role === "admin";
  modal(
    s.reference,
    `<div class="finance-detail-heading"><div><h3>${esc(s.driver_name)}</h3><p>${date(s.created_at)} · ${s.parcel_count} colis · ${financePeriod(s)}</p></div>${financeStatus(s.status)}${s.status==="Soldé"?'<span class="billing-status billing-paid">Paid</span>':""}</div>${s.cancelled_at ? `<div class="finance-cancelled">${icon("help")}Relevé annulé le ${date(s.cancelled_at)} · ${esc(s.cancel_reason)}. Les montants historiques ci-dessous ne sont plus exigibles.</div>` : ""}<div class="finance-detail-summary"><span>COD déclaré <b>${centMoney(s.cod_cents)} MAD</b></span><span>Commission <b>${centMoney(s.commission_cents)} MAD</b></span><span>Retenue autorisée <b>${centMoney(s.retained_cents)} MAD</b></span></div><div class="finance-mode-line">${icon("return")}${financeMode(s.mode)} · Barème figé v${s.revision}</div><div class="finance-balance-grid">${financeBalanceCard(s, "cash")}${financeBalanceCard(s, "commission")}</div><div class="finance-detail-tabs">${[
      ["parcels", "Colis du relevé"],
      ["transactions", "Règlements"],
      ["audit", "Historique"],
    ]
      .map(
        ([key, title]) =>
          `<button class="${financeDetailTab === key ? "active" : ""}" onclick="financeDetailTab='${key}';renderDriverStatement()">${title}${key === "transactions" ? ` <span>${transactions.length}</span>` : ""}</button>`,
      )
      .join(
        "",
      )}</div><div class="finance-detail-content">${financeDetailTab === "parcels" ? financeLinesTable(lines) : financeDetailTab === "transactions" ? financeTransactionTable(transactions, false) : `<div class="timeline">${audit.map((a) => `<div class="timeline-item"><b>${esc(a.action)}</b><p>${financeAuditText(a.details)}</p><small>${esc(a.actor_name)} · ${date(a.created_at)}</small></div>`).join("")}</div>`}</div><div class="finance-detail-actions"><div>${admin && !s.cancelled_at ? `<button class="btn sm danger" onclick="cancelDriverStatement(${s.id})">Annuler ce relevé</button>` : ""}</div><button class="btn" onclick="billingDownload('livreur',${s.id},'pdf')">PDF</button><button class="btn" onclick="billingDownload('livreur',${s.id},'csv')">CSV</button><button class="btn" onclick="printDriverStatement(${s.id})">${icon("print")}Imprimer / PDF</button></div>`,
    true,
  );
}
function financeAuditText(d) {
  return (
    [
      d.transaction_id ? "Écriture #" + d.transaction_id : "",
      d.amount_cents !== undefined ? centMoney(d.amount_cents) + " MAD" : "",
      d.reference ? "Réf. " + esc(d.reference) : "",
      d.reason ? esc(d.reason) : "",
      d.mode ? financeMode(d.mode) : "",
      d.revision ? "Barème v" + d.revision : "",
    ]
      .filter(Boolean)
      .join(" · ") || "Opération enregistrée dans le journal."
  );
}
function financeTransactionTable(rows, globalView) {
  if (!rows.length)
    return empty(
      "Aucun règlement enregistré",
      "Les remises COD et paiements de commission apparaîtront ici.",
    );
  return simpleTable(
    [
      "Écriture / Date",
      ...(globalView ? ["Livreur / Relevé"] : []),
      "Flux",
      "Montant",
      "Mode / Référence",
      "État",
      "",
    ],
    rows.map((t) => [
      `<span class="mono">Écriture #${t.id}</span><span class="sub">${date(t.paid_on)}</span>`,
      ...(globalView
        ? [
            `${esc(t.driver_name)}<span class="sub"><button class="tracking" onclick="openDriverStatement(${t.statement_id},'transactions')">${statementRef(t.statement_id)}</button></span>`,
          ]
        : []),
      `<span class="finance-flow ${t.kind}">${icon(t.kind === "cash" ? "download" : "upload")}${t.kind === "cash" ? "Remise COD" : "Commission"}</span>`,
      `<strong class="${t.voided_at ? "finance-strike" : ""}">${centMoney(t.amount_cents)} MAD</strong>`,
      `${esc(t.method)}<span class="sub">${esc(t.reference)}</span>${t.note ? `<span class="sub finance-tx-note">${esc(t.note)}</span>` : ""}`,
      t.voided_at
        ? `<span class="tag bad">Annulée</span><span class="sub finance-tx-note">${esc(t.void_reason)}</span>`
        : '<span class="tag good">Enregistrée</span>',
      S.user.role === "admin" && !t.voided_at
        ? `<button class="icon-btn" onclick="voidDriverTransaction(${t.id},${t.statement_id})" title="Annuler cette écriture">${icon("return")}</button>`
        : "—",
    ]),
  );
}
function recordDriverTransaction(kind) {
  const s = financeDetail.statement,
    cash = kind === "cash",
    remaining = s[cash ? "cash_remaining_cents" : "commission_remaining_cents"],
    key = financeKey();
  modal(
    cash
      ? "Enregistrer une remise COD"
      : "Enregistrer un paiement de commission",
    form(
      `<div class="full finance-payment-context"><span class="stat-icon ${cash ? "" : "green"}">${icon(cash ? "download" : "upload")}</span><div><strong>${esc(s.driver_name)} · ${s.reference}</strong><p>${cash ? "Livreur → ORIENTAL24" : "ORIENTAL24 → livreur"}</p></div><div><span>Solde restant</span><b>${centMoney(remaining)} MAD</b></div></div>${input("amount", "Montant (MAD)", centInput(remaining), "number", true, `min="0.01" max="${centInput(remaining)}" step="0.01"`)}${select(
        "method",
        "Mode de règlement",
        [
          ["Espèces", "Espèces"],
          ["Virement", "Virement"],
          ["Chèque", "Chèque"],
        ],
      )}${input("reference", "Référence de reçu / transaction", "", "text", true, 'maxlength="100"')}${input("paid_on", "Date du règlement", financeDay(), "date", true, `max="${financeDay()}"`)}${textarea("note", "Commentaire (facultatif)")}<div class="full form-hint orange">Enregistrez uniquement un paiement effectivement reçu ou versé. Cette saisie ne déclenche aucun virement. Une remise partielle est possible.</div>`,
      "Confirmer le règlement",
    ),
  );
  bindForm(async (d) => {
    const result = await api(
      "/driver-finance/statements/" + s.id + "/transactions",
      "POST",
      { ...d, kind, request_key: key },
    );
    await refresh();
    await renderView();
    await openDriverStatement(s.id, "transactions");
    toast(
      result.already_recorded
        ? "Écriture déjà enregistrée, aucun doublon."
        : "Règlement enregistré et solde recalculé",
    );
  });
}
function voidDriverTransaction(tid, sid) {
  modal(
    "Annuler une écriture",
    form(
      `<div class="full form-hint orange">L’écriture #${tid} restera visible, avec son motif d’annulation. Le solde du relevé sera réouvert. Aucun paiement réel n’est remboursé ou annulé automatiquement.</div>${textarea("reason", "Motif de correction", "", true)}`,
      "Annuler l’écriture",
    ),
  );
  bindForm(async (d) => {
    await api("/driver-finance/transactions/" + tid + "/void", "POST", d);
    await refresh();
    await renderView();
    await openDriverStatement(sid, "transactions");
    toast("Écriture annulée, historique conservé");
  });
}
function cancelDriverStatement(id) {
  modal(
    "Annuler le relevé " + statementRef(id),
    form(
      `<div class="full form-hint orange">Les écritures actives doivent d’abord être annulées et justifiées. Le relevé restera dans l’historique ; ses colis pourront être repris dans un nouveau relevé. Une facture client existante reste indépendante.</div>${textarea("reason", "Motif de l’annulation", "", true)}`,
      "Annuler le relevé",
    ),
  );
  bindForm(async (d) => {
    await api("/driver-finance/statements/" + id + "/cancel", "POST", d);
    await refresh();
    await renderView();
    await openDriverStatement(id, "audit");
    toast("Relevé annulé, colis libérés pour un nouveau rapprochement");
  });
}
async function printDriverStatement(id) {
  const owner = S?.user?.id;
  try {
    const d = await api("/driver-finance/statements/" + id);
    if (S?.user?.id !== owner) return;
    await doPrint(driverInvoicePrintHTML(d), (root) => { if (S?.user?.id !== owner) { root.innerHTML=""; throw Error("Session modifiée. Rouvrez le relevé."); } paginateDriverInvoice(root, d); });
  } catch (e) { toast(e.message, true); }
}
function resetDriverFinance() {
  financeData = null;
  financeDrivers = [];
  financeDetail = null;
  financePreview = null;
  financeTab = "statements";
  financeFilters = { driver: "", status: "", query: "" };
  financePage = 1;
}

/* v1.5.3 « Fin de journée » — caisse journalière par livreur : calcul à l’instant côté serveur,
   clôture tracée par Admin (écart = attendu − reçu), réouverture motivée. Indépendant des relevés périodiques. */
let financeDayStr = new Date().toISOString().slice(0, 10);
  financeDayRows = [];
const dayCents = (v) => centMoney(v || 0);
function financeDayStatus(r) {
  if (!r.close) return `<span class="tag">Ouverte</span>`;
  if (r.close.status === "Rouvert")
    return `<span class="tag purple" title="Rouverte le ${date(r.close.reopened_at)} : ${esc(r.close.reopen_note || "")}">Rouverte</span>`;
  return r.variance_cents
    ? `<span class="tag bad" title="Attendu ${dayCents(r.expected_cents)} · reçu ${dayCents(r.received_cents)} MAD">Écart ${dayCents(Math.abs(r.variance_cents))} MAD ${r.variance_cents > 0 ? "manquant" : "excédent"}</span>`
    : `<span class="tag good">Clôturée</span>`;
}
function financeDaysShell() {
  return `<div class="card-head"><div><h3>Fin de journée — caisse par livreur</h3><p>Instantané du jour : livrés, COD, commissions du barème (à la ville), attendu caisse, remise et écart. Aucun effet sur les relevés périodiques.</p></div><div class="flex"><input id="finance-day" type="date" aria-label="Jour à contrôler" value="${financeDayStr}" max="${new Date().toISOString().slice(0, 10)}" onchange="financeDayStr=this.value;loadFinanceDays()"><button class="icon-btn" onclick="loadFinanceDays()" title="Recalculer la journée">${icon("refresh")}</button></div></div><div id="finance-days" class="pilotage-loading">${icon("clock")} Calcul de la journée…</div>`;
}
async function loadFinanceDays() {
  const host = $("#finance-days");
  if (!host) return;
  try {
    const rows = await api((S.user.role === "admin" ? "/driver-days?day=" : "/driver-days/me?day=") + financeDayStr);
    if (!$("#finance-days")) return;
    financeDayRows = rows;
    host.innerHTML = !rows.length
      ? `<div class="form-hint">Aucun livreur actif sur cette journée.</div>`
      : `<div class="table-wrap"><table><thead><tr><th>Livreur</th><th>Journée</th><th>COD brut</th><th>Commissions</th><th>Attendu caisse</th><th>Reçu</th><th>Statut</th>${S.user.role === "admin" ? "<th></th>" : ""}</tr></thead><tbody>${rows.map((r, i) => `<tr><td><div class="recipient"><span class="avatar">${initials(r.driver)}</span><strong>${esc(r.driver)}</strong><span class="sub">${r.mode === "net" ? "Règlement net" : "Règlement brut"}${r.barême ? "" : " · barème manquant"}</span></div></td><td><strong>${r.livres} livré(s)</strong><span class="sub">${r.retournes} retourné(s) · ${r.refuses} refusé(s)</span></td><td><strong>${dayCents(r.cod_cents)}</strong> <span class="muted" style="font-size:9px">MAD</span></td><td>${r.barême ? dayCents(r.commission_cents) + " MAD" : '<span class="muted">—</span>'}</td><td><strong>${dayCents(r.expected_cents)}</strong> <span class="muted" style="font-size:9px">MAD</span></td><td>${r.close && r.close.status === "Clôturé" ? `<strong>${dayCents(r.received_cents)}</strong> MAD${r.close.reference ? `<span class="sub">${esc(r.close.reference)}</span>` : ""}` : '<span class="muted">—</span>'}</td><td>${financeDayStatus(r)}</td>${S.user.role === "admin" ? `<td>${r.closed ? `<button class="btn sm" onclick="reopenDay(${i})">${icon("return")}Rouvrir</button>` : `<button class="btn primary sm" onclick="closeDayForm(${i})">${icon("check")}Clôturer</button>`}</td>` : ""}</tr>`).join("")}</tbody></table></div><p class="pilotage-small-note">Attendu caisse = COD des colis « Livré » ce jour (moins la commission en règlement net). Le rapprochement bancaire continue de suivre les relevés périodiques.</p>`;
  } catch (e) {
    if ($("#finance-days")) $("#finance-days").innerHTML = `<div class="form-error">${esc(e.message)}</div>`;
  }
}
function closeDayForm(i) {
  const r = financeDayRows[i];
  if (!r) return;
  modal(
    `Clôturer la journée de ${r.driver}`,
    form(
      `<div class="form-hint"><b>${financeDayStr}</b> — ${r.livres} livré(s), COD brut <b>${dayCents(r.cod_cents)} MAD</b>, commissions ${r.barême ? dayCents(r.commission_cents) + " MAD" : "sans barème (0,00)"} → attendu caisse <b>${dayCents(r.expected_cents)} MAD</b>. La clôture fige un instantané tracé : l'écart éventuel restera affiché.</div>${input("received_mad", "Remise réellement reçue (MAD)", (r.expected_cents / 100).toFixed(2), "number", true, 'min="0" step="0.01"')}${input("reference", "Référence de la remise (reçu, caisse…)", "", "text", false)}${textarea("note", "Note (facultative)", "")}`,
    ),
  );
  bindForm(async (d) => {
    await api("/driver-days", "POST", { driver_id: r.driver_id, day: financeDayStr, received_mad: d.received_mad, reference: d.reference, note: d.note });
    await saved("Journée clôturée");
    loadFinanceDays();
  });
}
function reopenDay(i) {
  const r = financeDayRows[i];
  if (!r || !r.close) return;
  modal(
    `Rouvrir la journée de ${r.driver} (${r.day})`,
    form(
      `<div class="form-hint">La clôture du ${r.day} (reçu ${dayCents(r.close.received_cents)} MAD${r.close.reference ? ", réf. " + esc(r.close.reference) : ""}) sera <b>annulée</b> — elle pourra être refaite ensuite. Le motif reste visible dans l'historique financier.</div>${textarea("note", "Motif de la réouverture (obligatoire)", "", true)}`,
    ),
  );
  bindForm(async (d) => {
    await api(`/driver-days/${r.close.id}/reopen`, "POST", { note: d.note });
    await saved("Journée rouverte");
    loadFinanceDays();
  });
}

/* v1.6.1 « Conciliation banque » : collation du relevé bancaire (CSV/paste) avec les clôtures
   de journée des livreurs — traitement 100 % local, rien n'est enregistré. */
let bankReport = null;
function bankShell() {
  return `<div class="card-head"><div><h3>Rapprochement bancaire — remises des livreurs</h3><p>Collez le relevé de la banque (ou choisissez le fichier CSV) : chaque ligne est rapprochée de la <b>clôture de caisse</b> du même jour — même montant (±0,5 %), la référence quand elle correspond. Traitement local : <b>rien n'est envoyé ni enregistré</b>.</p></div>${icon("wallet")}</div>
  <div class="bank-grid"><div><label class="lbl" for="bank-file">Fichier CSV (banque)</label><label class="btn sm" style="display:inline-block">${icon("download")}Charger un fichier<input id="bank-file" type="file" accept=".csv,text/csv,text/plain" style="display:none" onchange="bankFile(this)"></label><div class="field" style="margin-top:10px"><label for="bank-text">…ou collez les lignes (une par remise)</label><textarea id="bank-text" rows="6" placeholder="23/09/2026 ; VIREMENT-2026-221 ; 850,10\n24/09/2026 ; Remise guichet Amine ; 1 224,50"></textarea></div><div class="form-hint">Colonnes reconnues : date (JJ/MM/AAAA ou AAAA-MM-JJ), montant (virgule ou point, espaces tolérés), libellé/référence. Séparateur « ; », « , » ou tabulation détecté automatiquement.</div><button class="btn primary" style="margin-top:12px" onclick="bankRun()">${icon("check")}Rapprocher</button></div><div id="bank-result">${bankReport ? bankResultHTML() : `<div class="form-hint">Le rapport apparaîtra ici après le chargement du relevé.</div>`}</div></div>`;
}
function bankFile(input) {
  const f = input.files && input.files[0];
  if (!f) return;
  const r = new FileReader();
  r.onload = () => { $("#bank-text").value = String(r.result || ""); toast("Relevé chargé : " + f.name); };
  r.readAsText(f);
}
function bankParseAmount(x) {
  const t = String(x || "").replace(/[\s\u202f]/g, "").replace(/MAD/gi, "").replace(",", ".");
  if (!/^[+-]?\d+(\.\d{1,2})?$/.test(t)) return null;
  const v = parseFloat(t);
  return Number.isFinite(v) ? v : null;
}
function bankParseDate(x) {
  const t = String(x || "").trim();
  let m = t.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  m = t.match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/);
  if (m) return `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`;
  return null;
}
function bankParse(text) {
  const lines = String(text || "").split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length) throw Error("Aucune ligne à rapprocher.");
  const probe = lines[0];
  const sep = (probe.match(/;/g) || []).length >= (probe.match(/,/g) || []).length ? ";" : probe.includes("\t") ? "\t" : ",";
  return lines.map((l, i) => {
    const cells = l.split(sep).map((c) => c.trim());
    const date = cells.map(bankParseDate).find(Boolean) || null;
    const amounts = cells.map(bankParseAmount).filter((v) => v !== null && v > 0);
    const amount = amounts.length ? amounts[amounts.length - 1].toFixed(2) : null;
    const label = cells.filter((c) => c && bankParseDate(c) === null && bankParseAmount(c) === null).join(" ");
    return { n: i + 1, raw: l, date, amount: amount === null ? null : +amount, label };
  }).filter((r) => r.date || r.amount !== null);
}
async function bankRun() {
  try {
    assertAdminBank();
    const parsed = bankParse($("#bank-text").value);
    const dates = [...new Set(parsed.map((r) => r.date).filter(Boolean))];
    if (!dates.length) throw Error("Aucune date exploitable dans les lignes fournies.");
    const expected = [];
    for (const day of dates) {
      const rows = await api("/driver-days?day=" + day);
      rows.forEach((r) => {
        if (r.close && r.close.status === "Clôturé" && r.received_cents > 0)
          expected.push({ day, driver: r.driver, amount: r.received_cents / 100, reference: r.close.reference || "", used: null });
      });
    }
    const report = parsed.map((b) => {
      if (b.amount === null || !b.date) return { ...b, match: null, reason: "ligne incomplète (date ou montant illisible)" };
      const pool = expected.filter((e) => !e.used && e.day === b.date && Math.abs(e.amount - b.amount) <= Math.max(0.005 * b.amount, 0.01));
      let hit = pool.find((e) => b.label && e.reference && (b.label.toUpperCase().includes(e.reference.toUpperCase()) || e.reference.toUpperCase().includes(b.label.toUpperCase().split(" ")[0] || "Ø")));
      if (!hit) hit = pool[0];
      if (hit) { hit.used = b.n; return { ...b, match: hit }; }
      return { ...b, match: null, reason: expected.some((e) => e.day === b.date) ? "aucun dépôt clôturé à ce montant ce jour-là" : "aucune clôture de caisse clôturée ce jour-là" };
    });
    bankReport = { lines: report, expected, dates };
    $("#bank-result").innerHTML = bankResultHTML();
  } catch (e) { toast(e.message, true); }
}
function assertAdminBank() { if (S.user.role !== "admin") throw Error("Réservé à l'administration."); }
function bankResultHTML() {
  const r = bankReport;
  const matched = r.lines.filter((l) => l.match).length;
  const unused = r.expected.filter((e) => !e.used);
  const unmatchedTotal = unused.reduce((n, e) => n + e.amount, 0);
  return `<section class="stats" style="margin:16px 0 10px">${stat("Lignes du relevé", r.lines.length, "", "file", "blue", "Lignes exploitables")}${stat("Rapprochées", matched, "", "checkcircle", "green", "Même jour, même montant (±0,5 %)")}${stat("Non rapprochées", r.lines.length - matched, "", "alert", "bad", "À contrôler manuellement")}${stat("Dépôts sans ligne bancaire", unused.length, "", "wallet", "purple", unused.length ? money(unmatchedTotal) + " MAD constatés côté caisse" : "Tout est rapproché")}</section>
  <div class="table-wrap"><table><thead><tr><th>#</th><th>Date</th><th>Libellé</th><th>Montant</th><th>Verdict</th></tr></thead><tbody>${r.lines.map((l) => `<tr class="bank-line"><td>${l.n}</td><td>${l.date || "<span class='muted'>—</span>"}</td><td>${esc(l.label || l.raw)}</td><td><strong>${l.amount === null ? "—" : money(l.amount) + " MAD"}</strong></td><td>${l.match ? `<span class="tag good">${icon("check")}Rapprochée → ${esc(l.match.driver)}${l.match.reference ? ` · ${esc(l.match.reference)}` : ""}</span>` : `<span class="tag warn" title="${esc(l.reason)}">Non rapprochée</span>`}</td></tr>`).join("")}</tbody></table></div>
  ${unused.length ? `<div class="form-hint" style="margin-top:10px">Dépôts clôturés sans ligne bancaire : ${unused.map((e) => `<span class="tag">${e.day} · ${esc(e.driver)} · ${money(e.amount)} MAD</span>`).join(" ")}</div>` : `<p class="form-hint green" style="margin-top:10px">${icon("checkcircle")}Toutes les clôtures des jours couverts ont une ligne bancaire.</p>`}`;
}
window.bankRun = bankRun; window.bankFile = bankFile;
