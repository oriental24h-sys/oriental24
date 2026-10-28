/* Commande avec échange — alerte livreur + billet de reprise.
   Le serveur crée automatiquement la reprise EC<tracking> quand une commande
   « échange » passe à Livré ; le livreur doit récupérer l'ancien article. */
const O24_EXCHANGE_SOUND = '/static/audio/recupere-echange.mp3';
let o24ExchangeAudio = null;

function o24ExchangeSpeak() {
  try {
    if (!('speechSynthesis' in window)) return;
    const u = new SpeechSynthesisUtterance('Récupère échange');
    u.lang = 'fr-FR';
    u.rate = 0.95;
    window.speechSynthesis.speak(u);
  } catch (e) { /* silence: l'alerte visuelle reste affichée */ }
}

function o24ExchangeSound() {
  try {
    if (!o24ExchangeAudio) {
      o24ExchangeAudio = new Audio(O24_EXCHANGE_SOUND);
      o24ExchangeAudio.preload = 'auto';
      o24ExchangeAudio.volume = 1;
    }
    const played = o24ExchangeAudio.play();
    if (played && played.catch) played.catch(() => o24ExchangeSpeak());
  } catch (e) { o24ExchangeSpeak(); }
}

function o24ExchangeTicket(x) {
  const settings = (typeof S !== 'undefined' && S && S.settings) || {};
  const company = String(settings.company || 'ORIENTAL24');
  const amount = x.amount === null || x.amount === undefined || x.amount === ''
    ? '—' : `${Number(x.amount).toFixed(2)} MAD`;
  return `<style>@page{size:80mm auto;margin:4mm}#print-root{padding:0;font-family:Arial,sans-serif;color:#111}
  .ex-ticket{width:72mm;margin:0 auto;text-align:center}
  .ex-ticket h1{font-size:15px;margin:0 0 2px;letter-spacing:.5px}
  .ex-ticket .ex-type{font-size:11px;font-weight:bold;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px}
  .ex-ticket .ex-track{font-family:ui-monospace,Menlo,monospace;font-size:19px;font-weight:bold;border:2px dashed #111;border-radius:4px;padding:7px 4px;margin:6px 0 9px;word-break:break-all}
  .ex-ticket table{width:100%;border-collapse:collapse;font-size:10px;text-align:left}
  .ex-ticket td{padding:3px 0;vertical-align:top;border-bottom:1px dotted #999}
  .ex-ticket td:first-child{color:#444;width:34%}
  .ex-ticket .ex-note{font-size:9px;margin-top:8px;line-height:1.4;text-align:left}
  </style>
  <div class="ex-ticket">
    <h1>${esc(company)}</h1>
    <p class="ex-type">Reprise après échange</p>
    <div class="ex-track" dir="ltr">${esc(x.tracking || '')}</div>
    <table><tbody>
      <tr><td>Destinataire</td><td><b>${esc(x.recipient || '—')}</b></td></tr>
      <tr><td>Téléphone</td><td dir="ltr">${esc(x.phone || '—')}</td></tr>
      <tr><td>Ville</td><td>${esc(x.city || '—')}</td></tr>
      <tr><td>Montant d'origine</td><td>${esc(amount)}</td></tr>
      <tr><td>Nature</td><td>Échange — ancien article à récupérer</td></tr>
    </tbody></table>
    <p class="ex-note">À récupérer chez le destinataire puis à remettre au Hub. Aucun encaissement sur ce billet. Billet interne ORIENTAL24.</p>
  </div>`;
}

async function o24ExchangePrint(id) {
  try {
    const data = await api('/parcels/' + id);
    const p = data.parcel || {};
    await doPrint(o24ExchangeTicket({
      tracking: p.tracking, recipient: p.recipient, phone: p.phone,
      city: p.city || p.current_hub_name || '', amount: p.amount,
    }));
  } catch (e) { toast(e.message || 'Impression impossible', true); }
}

function o24ExchangeAlert(x) {
  if (!x || !x.tracking) return;
  o24ExchangeSound();
  const body = `
    <div class="exchange-alert">
      <p class="exchange-alert-shout">Récupère échange</p>
      <p class="form-hint">La livraison est enregistrée. Récupérez l'ancien article chez le destinataire, puis remettez-le au Hub. La reprise reste comptée sur vous jusqu'à sa réception au Hub.</p>
      <div class="exchange-alert-track" dir="ltr">${esc(x.tracking)}</div>
      <table class="exchange-alert-table"><tbody>
        <tr><th>Destinataire</th><td>${esc(x.recipient || '—')}</td></tr>
        <tr><th>Téléphone</th><td dir="ltr">${esc(x.phone || '—')}</td></tr>
        <tr><th>Ville</th><td>${esc(x.city || '—')}</td></tr>
      </tbody></table>
      <div class="form-actions">
        <button type="button" class="btn" onclick="o24ExchangePrint(${Number(x.id)})">Imprimer le billet</button>
        <button type="button" class="btn primary" onclick="closeModal()">J'ai compris</button>
      </div>
      <p class="form-hint">Le son peut être rejoué : <button type="button" class="btn sm" onclick="o24ExchangeSound()">Écouter</button></p>
    </div>`;
  modal('Échange à récupérer', body);
}

/* Un livreur ne modifie jamais une reprise : c'est le Hub qui la réceptionne. */
function o24ExchangeCustodyStatus(status) {
  return status === 'Échange à récupérer' || status === 'Échange Réceptionné';
}
