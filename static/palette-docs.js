/* Documents d'une palette — disponibles pour TOUTE palette qui arrive :
   ticket (impression), CSV des CMD, ouverture, pièces jointes, bon de réception PDF.
   `kind` : `partner` (palette société) ou `transfer` (palette inter-Hub). */
function paletteDocsBase(kind, id) { return '/api/palette-docs/' + kind + '/' + Number(id) }
function o24AutoTrackingCode() {
  try { return [...crypto.getRandomValues(new Uint8Array(8))].map(x => x.toString(16).padStart(2, '0')).join(''); } catch (e) { return String(Date.now()); }
}
const PALETTE_NATURES = { partner: 'RÉCEPTION', transfer: 'RÉCEPTION', pickup: 'RAMASSAGE', return: 'RETOUR' }
function paletteRowActions(kind, id, opener) {
  const base = paletteDocsBase(kind, id), k = String(kind).replace(/[^a-z]/g, '');
  if (!['partner', 'transfer', 'pickup', 'return'].includes(k)) return '';
  return `<div class="pal-actions">`
    + `<a class="pal-ic" href="${base}/ticket.pdf" target="_blank" rel="noopener" title="Imprimer le ticket de palette" aria-label="Imprimer le ticket de palette">${icon('print')}</a>`
    + `<a class="pal-ic" href="${base}/colis.csv" title="Toutes les CMD de la palette en CSV (Excel)" aria-label="Exporter les CMD en CSV">${icon('file')}</a>`
    + `<button type="button" class="pal-ic" onclick="${opener}" title="Ouvrir la palette" aria-label="Ouvrir la palette">${icon('eye')}</button>`
    + `<button type="button" class="pal-ic" onclick="paletteAttachOpen('${k}',${Number(id)})" title="Pièces jointes (photo du bon, réserve)" aria-label="Pièces jointes">${icon('upload')}</button>`
    + `<a class="pal-ic" href="${base}/bon.pdf" target="_blank" rel="noopener" title="Bon de réception PDF (imprimable)" aria-label="Bon de réception PDF">${icon('download')}</a>`
    + `</div>`;
}
function paletteFileDataURL(file) {
  return new Promise((ok, ko) => {
    if (/^image\/(jpeg|png|webp)$/.test(file.type) && typeof podShrink === 'function') return podShrink(file).then(ok, ko);
    if (file.type === 'application/pdf') {
      const reader = new FileReader();
      reader.onload = () => ok(String(reader.result || ''));
      reader.onerror = () => ko(new Error('Fichier illisible.'));
      reader.readAsDataURL(file);
      return;
    }
    ko(new Error('Formats acceptés : photo JPEG/PNG/WebP ou PDF.'));
  });
}
async function paletteAttachOpen(kind, id) {
  const owner = S?.user?.id;
  const base = paletteDocsBase(kind, id);
  modal('Pièces jointes de la palette', '<p>Chargement…</p>', true);
  const node = document.querySelector('#modal-root .modal');
  const current = () => node && node.isConnected && S?.user?.id === owner;
  const draw = async () => {
    const d = await api(base.replace('/api', '') + '/attachments');
    if (!current()) return;
    node.querySelector('.modal-body').innerHTML = `
      <p class="form-hint">Photo du bon signé, réserve transporteur, écart constaté… ${Math.round((d.max_bytes || 1500000) / 1000)} Ko maximum par fichier.</p>
      <form id="pal-attach-form" class="pal-attach-form">
        <label class="field"><span>Fichier (photo ou PDF)</span><input type="file" id="pal-attach-file" accept="image/jpeg,image/png,image/webp,application/pdf" required></label>
        <label class="field"><span>Note</span><input type="text" id="pal-attach-note" maxlength="300" placeholder="Ex. réserve transporteur : 2 colis écrasés"></label>
        <div class="form-error" id="pal-attach-error" style="display:none"></div>
        <div class="form-actions"><button type="submit" class="btn primary">${icon('upload')}Ajouter la pièce jointe</button></div>
      </form>
      ${d.rows.length ? `<div class="table-wrap"><table><thead><tr><th>Pièce</th><th>Note</th><th>Ajoutée par</th><th></th></tr></thead><tbody>${d.rows.map(r => `<tr><td><a href="/api/palette-docs/attachments/${r.id}" target="_blank" rel="noopener" class="tracking">${r.mime === 'application/pdf' ? 'PDF' : 'Photo'} · ${Math.max(1, Math.round(r.size / 1024))} Ko</a></td><td>${esc(r.note || '—')}</td><td>${esc(r.actor || '')}<span class="sub">${date(r.created_at)}</span></td><td><button type="button" class="btn sm danger" onclick="paletteAttachDelete(${r.id},'${kind}',${Number(id)})">Retirer</button></td></tr>`).join('')}</tbody></table></div>` : '<p class="sub">Aucune pièce jointe pour cette palette.</p>'}
      <div class="form-actions"><button type="button" class="btn" onclick="closeModal()">Fermer</button></div>`;
    const form = node.querySelector('#pal-attach-form');
    form.onsubmit = async (e) => {
      e.preventDefault();
      const file = form.querySelector('#pal-attach-file').files[0];
      const error = form.querySelector('#pal-attach-error');
      error.style.display = 'none';
      if (!file) { error.textContent = 'Choisissez un fichier.'; error.style.display = 'block'; return; }
      const button = form.querySelector('button[type=submit]');
      button.disabled = true;
      try {
        const dataUrl = await paletteFileDataURL(file);
        await api(base.replace('/api', '') + '/attachments', 'POST', { data_url: dataUrl, note: form.querySelector('#pal-attach-note').value });
        if (!current()) return;
        toast('Pièce jointe ajoutée');
        await draw();
      } catch (err) {
        if (!current()) return;
        error.textContent = err.message;
        error.style.display = 'block';
        button.disabled = false;
      }
    };
  };
  try { await draw(); } catch (e) { if (current()) node.querySelector('.modal-body').innerHTML = `<p class="form-hint orange">${esc(e.message)}</p><div class="form-actions"><button class="btn" onclick="closeModal()">Fermer</button></div>`; }
}
async function paletteAttachDelete(aid, kind, id) {
  if (!confirm('Retirer cette pièce jointe ?')) return;
  try {
    await api('/palette-docs/attachments/' + aid, 'DELETE', {});
    toast('Pièce jointe retirée');
    await paletteAttachOpen(kind, id);
  } catch (e) { toast(e.message, true); }
}
