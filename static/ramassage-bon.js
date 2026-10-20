/* ORIENTAL24 — Bons de ramassage vendeur.
   Sélection de colis « Créé », validation (-> Confirmé), impression du bon,
   et réception scannée côté Hub (-> Ramassé). APIs /api/ramassage-bons/*. */

const RB_DANGER = new Set(["Annulé"]);

function rbStatusTag(s) {
  return tag(s);
}

/* ------------------------------------------------------------- Vue liste (client/admin) */
async function ramassageBonsView() {
  const bons = await api("/ramassage-bons");
  const canCreate = ["client", "admin"].includes(S.user.role);
  const rows = bons.map((b) => {
    const mine = S.user.role === "admin" || b.client_id === S.user.id;
    const actions = [
      `<button class="btn sm" onclick="openRamassageBon(${b.id})">${icon("eye")}Ouvrir</button>`,
      `<button class="btn sm" onclick="printRamassageBon(${b.id})">${icon("print")}Imprimer</button>`,
    ];
    if (b.status === "Brouillon" && mine)
      actions.push(`<button class="btn sm primary" onclick="validateRamassageBon(${b.id})">${icon("check")}Valider</button>`);
    if ((b.status === "Brouillon" && mine) || (b.status === "Confirmé" && S.user.role === "admin"))
      actions.push(`<button class="btn sm danger" onclick="cancelRamassageBon(${b.id})">${icon("close")}Annuler</button>`);
    return [
      `<span class="tracking">${esc(b.reference)}</span>`,
      `<strong>${esc(b.hub_name || "—")}</strong><span class="sub">${esc(b.city_name || "")} · ${esc(b.client_company || b.client_name || "")}</span>`,
      date(b.pickup_date),
      `<strong>${b.received}/${b.count}</strong><span class="sub"> colis</span>`,
      rbStatusTag(b.status),
      actions.join(" "),
    ];
  });
  return (
    heading(
      "Ramassages",
      "Choisissez vos colis, validez le bon : ils passent « Confirmé ». Le Hub les réceptionne ensuite au scan.",
      canCreate ? `<button class="btn primary" onclick="newRamassageBon()">${icon("plus")}Demander un ramassage</button>` : "",
    ) +
    `<section class="stats">
      ${stat("Bons", bons.length, "", "file", "blue", "Tous statuts")}
      ${stat("Brouillons", bons.filter((b) => b.status === "Brouillon").length, "", "edit", "", "À valider")}
      ${stat("En attente Hub", bons.filter((b) => ["Confirmé", "En cours"].includes(b.status)).length, "", "truck", "purple", "Confirmés / en réception")}
      ${stat("Reçus au Hub", bons.filter((b) => b.status === "Reçu").length, "", "checkcircle", "green", "Réceptionnés")}
    </section>
    <section class="card"><div class="card-head"><h3>Bons de ramassage</h3><span class="tag">${bons.length} bon(s)</span></div>
    ${simpleTable(["Référence", "Hub / Client", "Date prévue", "Réception", "Statut", ""], rows)}
    </section>`
  );
}

/* ------------------------------------------------------------- Création d'un bon */
async function newRamassageBon() {
  const isAdmin = S.user.role === "admin";
  const clientOptions = isAdmin
    ? S.users.filter((u) => u.role === "client" && u.active).map((u) => [u.id, `${u.company || u.name} · ${u.email}`])
    : [];
  const hubOptions = S.hubs.filter((h) => h.active).map((h) => [h.id, `${h.name} · ${h.city || ""}`]);
  const today = new Date().toISOString().slice(0, 10);
  modal(
    "Demander un ramassage",
    form(
      `${isAdmin ? select("client_id", "Client", [["", "Choisir un client"], ...clientOptions]) : ""}
       ${select("hub_id", "Hub de réception", hubOptions)}
       ${input("pickup_date", "Date souhaitée", today, "date", true, `min="${today}"`)}
       ${input("phone", "Téléphone", S.user.phone || "", "tel", true)}
       ${textarea("address", "Adresse de ramassage", "", true)}
       ${textarea("note", "Note (facultatif)", "", false)}
       <div class="field full">
         <label>Colis à ramasser (état « Créé ») *</label>
         <div id="rb-eligible" style="display:grid;gap:6px;max-height:260px;overflow:auto;border:1px solid var(--line);border-radius:8px;padding:10px">
           <span class="sub">Chargement…</span>
         </div>
         <small class="sub" id="rb-eligible-count"></small>
       </div>
       <div class="full form-hint">La validation passera les colis choisis en « Confirmé ». Un colis ne peut appartenir qu’à un seul bon actif.</div>`,
      "Créer le brouillon",
    ),
    true,
  );
  const clientSel = document.getElementById("f-client_id");
  const loadEligible = async () => {
    const box = document.getElementById("rb-eligible");
    try {
      const cid = isAdmin && clientSel ? clientSel.value : "";
      const rows = await api("/ramassage-bons/eligible" + (cid ? "?client_id=" + encodeURIComponent(cid) : ""));
      box.innerHTML = rows.length
        ? rows
            .map(
              (p) =>
                `<label class="check-label" style="margin:0"><input type="checkbox" name="colis_${p.id}" value="${p.id}">
                 <span><b>${esc(p.tracking)}</b> · ${esc(p.recipient || "")}<small class="sub">${esc(p.city || "")} · ${esc(p.status)}</small></span></label>`,
            )
            .join("")
        : empty("Aucun colis éligible", "Tous vos colis « Créé » sont déjà dans un bon ou traités.");
      document.getElementById("rb-eligible-count").textContent = rows.length
        ? `${rows.length} colis éligible(s)`
        : "";
    } catch (e) {
      box.innerHTML = `<span class="sub">${esc(e.message)}</span>`;
    }
  };
  if (clientSel) clientSel.onchange = loadEligible;
  await loadEligible();
  bindForm(async (d) => {
    const ids = [
      ...document.querySelectorAll("#rb-eligible input[type=checkbox]:checked"),
    ].map((x) => Number(x.value));
    if (!ids.length) throw Error("Sélectionnez au moins un colis.");
    const payload = {
      hub_id: Number(d.hub_id),
      pickup_date: d.pickup_date,
      phone: d.phone,
      address: d.address,
      note: d.note || "",
      parcel_ids: ids,
    };
    if (isAdmin) payload.client_id = Number(d.client_id);
    await api("/ramassage-bons", "POST", payload);
    await saved("Brouillon de bon de ramassage créé");
  });
}

/* ------------------------------------------------------------- Détail d'un bon */
async function openRamassageBon(id) {
  const b = await api("/ramassage-bons/" + id);
  const mine = S.user.role === "admin" || b.client_id === S.user.id;
  const head = `
    <div class="ops-document-head">
      <div>
        <h3>${esc(b.reference)} ${rbStatusTag(b.status)}</h3>
        <p><b>${esc(b.hub_name || "—")}</b> · ${esc(b.city_name || "")}<br>
           ${esc(b.address)} · ${esc(b.phone)}<br>
           Date prévue : ${date(b.pickup_date)}${b.note ? "<br>Note : " + esc(b.note) : ""}</p>
      </div>
      <div style="text-align:right">
        <p class="sub">${esc(b.client_company || b.client_name || "")}</p>
        <p class="sub">Réception : <b>${b.received}/${b.count}</b></p>
      </div>
    </div>`;
  const linesTable = simpleTable(
    ["Suivi", "Destinataire", "Ville", "Statut colis", "Réceptionné"],
    b.lines.map((l) => [
      `<span class="tracking">${esc(l.tracking)}</span>`,
      esc(l.recipient || "—"),
      esc(l.city || "—"),
      tag(l.parcel_status || ""),
      l.received_at ? `<span class="tag good">${icon("check")}${date(l.received_at)}</span>` : '<span class="sub">—</span>',
    ]),
  );
  const actions = [];
  if (b.status === "Brouillon" && mine)
    actions.push(`<button class="btn primary" onclick="validateRamassageBon(${b.id})">${icon("check")}Valider le bon</button>`);
  if ((b.status === "Brouillon" && mine) || (b.status === "Confirmé" && S.user.role === "admin"))
    actions.push(`<button class="btn danger" onclick="cancelRamassageBon(${b.id})">${icon("close")}Annuler le bon</button>`);
  actions.push(`<button class="btn" onclick="printRamassageBon(${b.id})">${icon("print")}Imprimer</button>`);
  modal(
    "Bon de ramassage · " + b.reference,
    `${head}<section class="card" style="margin:14px 0">${linesTable}</section>
     <div class="form-actions">${actions.join("")}</div>`,
    true,
  );
}

/* ------------------------------------------------------------- Validation / annulation */
function validateRamassageBon(id) {
  modal(
    "Valider le bon de ramassage",
    form(
      `<div class="full form-hint orange">Tous les colis de ce bon passeront de « Créé » à <b>« Confirmé »</b>.
       Ils ne pourront plus être modifiés et attendront la réception scannée au Hub.</div>
       <label class="full check-label"><input type="checkbox" name="confirmed" required>
       Je confirme la sélection et la validation du bon.</label>`,
      "Confirmer la validation",
    ),
  );
  bindForm(async () => {
    await api("/ramassage-bons/" + id + "/validate", "POST", {});
    await saved("Bon validé · colis passés « Confirmé »");
  });
}

function cancelRamassageBon(id) {
  modal(
    "Annuler le bon de ramassage",
    form(
      `${textarea("reason", "Motif de l’annulation", "", true)}
       <div class="full form-hint">Les colis d’un bon confirmé reprennent l’état « Créé » et redeviennent éligibles.</div>`,
      "Confirmer l’annulation",
    ),
  );
  bindForm(async (d) => {
    await api("/ramassage-bons/" + id + "/cancel", "POST", { reason: d.reason });
    await saved("Bon annulé");
  });
}

/* ------------------------------------------------------------- Impression du bon */
async function printRamassageBon(id) {
  const b = await api("/ramassage-bons/" + id);
  const rows = b.lines
    .map(
      (l, i) =>
        `<tr><td>${i + 1}</td><td>${esc(l.tracking)}</td><td>${esc(l.recipient || "")}</td><td>${esc(l.city || "")}</td><td>${esc(l.parcel_status || "")}</td><td>${l.received_at ? date(l.received_at) : "—"}</td></tr>`,
    )
    .join("");
  const html = `<style>
      @page{size:A4;margin:14mm} body{font-family:Arial,Helvetica,sans-serif;color:#12203a;font-size:12px}
      .head{display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #071d3c;padding-bottom:10px;margin-bottom:14px}
      img{height:46px} h1{font-size:18px;margin:0 0 2px} h2{font-size:13px;margin:14px 0 6px}
      .meta{display:grid;grid-template-columns:1fr 1fr;gap:4px 18px;margin:8px 0}
      .meta b{display:inline-block;min-width:120px;color:#53667e}
      table{width:100%;border-collapse:collapse;margin-top:6px} th,td{border:1px solid #b9c2d0;padding:6px 8px;text-align:left}
      th{background:#eef2f8} .tag{display:inline-block;padding:2px 8px;border-radius:10px;background:#e7eefc;color:#0b3d91;font-weight:600}
      .sign{margin-top:34px;display:grid;grid-template-columns:1fr 1fr;gap:40px}.sign div{border-top:1px solid #53667e;padding-top:6px;color:#53667e}
      .foot{margin-top:16px;color:#7a869a;font-size:10px}
    </style>
    <div class="head"><img src="/static/wordmark.png" alt="ORIENTAL24">
      <div style="text-align:right"><h1>Bon de ramassage</h1>
        <span class="tag">${esc(b.status)}</span><p class="foot" style="margin:4px 0 0">${esc(b.reference)}</p></div></div>
    <div class="meta">
      <div><b>Client :</b> ${esc(b.client_company || b.client_name || "")}</div>
      <div><b>Hub de réception :</b> ${esc(b.hub_name || "")}</div>
      <div><b>Ville :</b> ${esc(b.city_name || "")}</div>
      <div><b>Date prévue :</b> ${date(b.pickup_date)}</div>
      <div><b>Adresse :</b> ${esc(b.address)}</div>
      <div><b>Téléphone :</b> ${esc(b.phone)}</div>
      ${b.note ? `<div style="grid-column:1/3"><b>Note :</b> ${esc(b.note)}</div>` : ""}
    </div>
    <h2>Colis du bon (${b.count}) — réceptionnés : ${b.received}</h2>
    <table><thead><tr><th>#</th><th>Suivi</th><th>Destinataire</th><th>Ville</th><th>Statut</th><th>Réceptionné le</th></tr></thead>
      <tbody>${rows}</tbody></table>
    <div class="sign"><div>Signature & cachet du Hub</div><div>Signature du client / chauffeur</div></div>
    <div class="foot">ORIENTAL24 · document interne de ramassage · édité le ${date(new Date().toISOString())} · ${esc(b.reference)}</div>`;
  await doPrint(html);
}

/* ------------------------------------------------------------- Réception Hub (scan) */
let rbScanId = null;

async function ramassageReceptionView() {
  const bons = await api("/ramassage-bons/hub/queue");
  const rows = bons.map((b) => [
    `<span class="tracking">${esc(b.reference)}</span>`,
    `<strong>${esc(b.client_company || b.client_name || "")}</strong><span class="sub">${esc(b.hub_name || "")}</span>`,
    date(b.pickup_date),
    `<strong>${b.received}/${b.count}</strong>`,
    rbStatusTag(b.status),
    `<button class="btn sm primary" onclick="openRamassageScan(${b.id})">${icon("scan")}Scanner la réception</button>`,
  ]);
  return (
    heading(
      "Réception des ramassages",
      "Scannez chaque colis des bons confirmés destinés à votre Hub. Il passe alors « Ramassé ».",
      `<button class="btn" onclick="renderView()">${icon("refresh")}Actualiser</button>`,
    ) +
    `<section class="card"><div class="card-head"><h3>Bons en attente de réception</h3><span class="tag">${bons.length}</span></div>
     ${simpleTable(["Référence", "Client / Hub", "Date", "Reçus / Total", "Statut", ""], rows)}
     </section>`
  );
}

function rbScanLinesHtml(b) {
  return simpleTable(
    ["Suivi", "Destinataire", "Ville", "Statut", "Réception"],
    b.lines.map((l) => [
      `<span class="tracking">${esc(l.tracking)}</span>`,
      esc(l.recipient || "—"),
      esc(l.city || "—"),
      tag(l.parcel_status || ""),
      l.received_at ? `<span class="tag good">${icon("check")} Reçu</span>` : '<span class="tag warn">En attente</span>',
    ]),
  );
}

async function openRamassageScan(id) {
  rbScanId = id;
  const b = await api("/ramassage-bons/" + id);
  modal(
    "Réception · " + b.reference,
    `<div class="ops-document-head"><div><h3>${esc(b.reference)} ${rbStatusTag(b.status)}</h3>
        <p>${esc(b.hub_name || "")} · ${esc(b.client_company || b.client_name || "")}<br>
        Progression : <b id="rb-scan-progress">${b.received}/${b.count}</b></p></div></div>
      <form id="rb-scan-form" class="field full" style="margin:12px 0">
        <label for="rb-scan-input">Scanner ou saisir le code de suivi</label>
        <input id="rb-scan-input" name="tracking" autocomplete="off" placeholder="Ex. O24-100004" required
               style="text-transform:uppercase;letter-spacing:1px;font-weight:600">
        <div class="form-actions"><button class="btn primary" type="submit">${icon("scan")}Valider la réception</button></div>
      </form>
      <div id="rb-scan-body">${rbScanLinesHtml(b)}</div>`,
    true,
  );
  const input = document.getElementById("rb-scan-input");
  input?.focus();
  document.getElementById("rb-scan-form").onsubmit = async (e) => {
    e.preventDefault();
    const tracking = input.value.trim();
    if (!tracking) return;
    try {
      const r = await api("/ramassage-bons/" + id + "/receive", "POST", { tracking });
      toast(r.already_received ? "Colis déjà réceptionné" : "Colis réceptionné · état « Ramassé »");
    } catch (err) {
      toast(err.message, true);
    }
    input.value = "";
    input.focus();
    await refreshRamassageScan(id);
  };
}

async function refreshRamassageScan(id) {
  try {
    const b = await api("/ramassage-bons/" + id);
    const body = document.getElementById("rb-scan-body");
    const prog = document.getElementById("rb-scan-progress");
    if (body) body.innerHTML = rbScanLinesHtml(b);
    if (prog) prog.textContent = `${b.received}/${b.count}`;
    if (b.status === "Reçu") {
      toast("Bon complet · tous les colis réceptionnés au Hub");
      setTimeout(() => {
        if (rbScanId === id) closeModal();
      }, 900);
      await renderView();
    }
  } catch (e) {
    /* le bon a peut-être été fermé ; on ignore l'actualisation */
  }
}
