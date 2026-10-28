/* Commande avec échange — alerte livreur + billet de reprise.
   Le serveur crée automatiquement la reprise EC<tracking> quand une commande
   « échange » passe à Livré ; le livreur doit récupérer l'ancien article.

   Son : les navigateurs (Chrome, Safari, Android, iOS) bloquent un audio lancé
   sans interaction. On « débloque » donc l'élément au premier toucher/clic, et
   on le réarme au moment du clic « Confirmer la livraison ». Replis successifs :
   MP3 → voix du navigateur → bip électronique. L'alerte visuelle reste toujours. */
const O24_EXCHANGE_SOUND = '/static/audio/recupere-echange.mp3';
let o24ExchangeAudio = null;
let o24ExchangeArmed = false;
let o24ExchangeFailed = false;
let o24AudioCtx = null;

function o24ExchangeElement() {
  if (!o24ExchangeAudio) {
    o24ExchangeAudio = new Audio(O24_EXCHANGE_SOUND);
    o24ExchangeAudio.preload = 'auto';
    o24ExchangeAudio.volume = 1;
    o24ExchangeAudio.setAttribute('playsinline', '');
    o24ExchangeAudio.addEventListener('error', () => { o24ExchangeFailed = true; });
  }
  return o24ExchangeAudio;
}

/* Débloque la lecture dans le geste utilisateur (silencieux, une seule fois). */
function o24ExchangeArm() {
  try {
    const a = o24ExchangeElement();
    if (!o24ExchangeArmed) {
      const previous = a.volume;
      a.volume = 0;
      const p = a.play();
      if (p && p.then) {
        p.then(() => {
          a.pause(); a.currentTime = 0; a.volume = previous; o24ExchangeArmed = true;
        }).catch(() => { a.volume = previous; });
      } else {
        a.pause(); a.currentTime = 0; a.volume = previous; o24ExchangeArmed = true;
      }
    }
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (Ctx) {
        o24AudioCtx = o24AudioCtx || new Ctx();
        if (o24AudioCtx.state === 'suspended') o24AudioCtx.resume();
      }
    } catch (e) { /* pas de WebAudio : on garde le MP3 */ }
  } catch (e) { /* rien à faire : le repli vocal prendra le relais */ }
}

/* Repli 2 : voix du navigateur (aucun fichier nécessaire). */
function o24ExchangeSpeak(onEnd) {
  try {
    if (!('speechSynthesis' in window)) { if (onEnd) onEnd(false); return; }
    const u = new SpeechSynthesisUtterance('Récupère échange');
    u.lang = 'fr-FR';
    u.rate = 0.95;
    u.onend = () => { if (onEnd) onEnd(true); };
    u.onerror = () => { if (onEnd) onEnd(false); };
    window.speechSynthesis.speak(u);
  } catch (e) { if (onEnd) onEnd(false); }
}

/* Repli 3 : bip électronique (fonctionne même si aucun fichier n'est déployé). */
function o24ExchangeBeep() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return false;
    o24AudioCtx = o24AudioCtx || new Ctx();
    if (o24AudioCtx.state === 'suspended') o24AudioCtx.resume();
    const now = o24AudioCtx.currentTime;
    [0, 0.28, 0.56].forEach((offset, index) => {
      const osc = o24AudioCtx.createOscillator();
      const gain = o24AudioCtx.createGain();
      osc.type = 'square';
      osc.frequency.value = index === 2 ? 1180 : 880;
      gain.gain.setValueAtTime(0.0001, now + offset);
      gain.gain.exponentialRampToValueAtTime(0.35, now + offset + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + offset + 0.22);
      osc.connect(gain).connect(o24AudioCtx.destination);
      osc.start(now + offset);
      osc.stop(now + offset + 0.24);
    });
    return true;
  } catch (e) { return false; }
}

/* Joue l'alerte avec replis, et signale si aucun son n'a pu sortir. */
function o24ExchangePlay(onResult) {
  const finish = (ok) => { if (onResult) onResult(ok); };
  let settled = false;
  const done = (ok) => { if (!settled) { settled = true; finish(ok); } };
  try {
    const a = o24ExchangeElement();
    a.currentTime = 0;
    a.volume = 1;
    const p = a.play();
    if (!p || !p.then) { done(true); return; }
    p.then(() => {
      o24ExchangeArmed = true;
      done(true);
    }).catch(() => {
      o24ExchangeSpeak((spoken) => {
        if (spoken) { done(true); return; }
        done(o24ExchangeBeep());
      });
    });
  } catch (e) {
    o24ExchangeSpeak((spoken) => { if (spoken) { done(true); return; } done(o24ExchangeBeep()); });
  }
  setTimeout(() => { if (!settled) done(o24ExchangeBeep()); }, 1200);
}

function o24ExchangeSound() {
  o24ExchangePlay((ok) => {
    if (!ok) toast('Son bloqué par le navigateur — touchez « Écouter » ou montez le volume.', true);
  });
}

/* Compatibilité avec l'ancien nom utilisé ailleurs. */
function o24ExchangeSpeakOnly() { o24ExchangeSpeak(); }

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
        <button type="button" class="btn exchange-listen" onclick="o24ExchangeSound()">▶ Écouter l'alerte</button>
        <button type="button" class="btn" onclick="o24ExchangePrint(${Number(x.id)})">Imprimer le billet</button>
        <button type="button" class="btn primary" onclick="closeModal()">J'ai compris</button>
      </div>
      <p class="form-hint" id="exchange-sound-state">Si vous n'entendez rien : touchez « Écouter l'alerte » et vérifiez le volume du téléphone.</p>
    </div>`;
  modal('Échange à récupérer', body);
  o24ExchangePlay((ok) => {
    const hint = document.querySelector('#exchange-sound-state');
    if (hint && !ok) hint.textContent = 'Le son a été bloqué par le navigateur : touchez « Écouter l’alerte » et montez le volume.';
    if (hint && ok) hint.textContent = "Alerte sonore diffusée. Touchez « Écouter l'alerte » pour la réentendre.";
  });
}

/* Un livreur ne modifie jamais une reprise : c'est le Hub qui la réceptionne. */
function o24ExchangeCustodyStatus(status) {
  return status === 'Échange à récupérer' || status === 'Échange Réceptionné';
}

/* Déblocage du son dès la première interaction (une seule fois). */
(function o24ExchangePrime() {
  const prime = () => { o24ExchangeArm(); };
  ['pointerdown', 'touchstart', 'keydown', 'click'].forEach((event) => {
    document.addEventListener(event, prime, { once: true, passive: true });
  });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') o24ExchangeArm();
  });
})();
