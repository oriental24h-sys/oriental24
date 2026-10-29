/* Printable A4 manifests for reception, return and hub-to-hub movements. */
function o24BonClean(value){
 if(value===null||value===undefined)return '';
 const text=String(value).trim();
 return !text||/^(undefined|null|nan)$/i.test(text)?'':text;
}
function o24BonHtml(data){
 const settings=(typeof S!=='undefined'&&S&&S.settings)||{};
 const company=o24BonClean(settings.company)||'ORIENTAL24 S.A.R.L.';
 const contact=[settings.public_address,settings.public_phone,settings.public_email].map(o24BonClean).filter(Boolean);
 const party=data.party||{},partyLines=(party.lines||[]).map(o24BonClean).filter(Boolean);
 const rows=(data.rows||[]).map(row=>`<tr><td class="o24-bon-track">${esc(o24BonClean(row.tracking)||'—')}</td><td>${esc(o24BonClean(row.city)||'—')}</td><td>${esc(o24BonClean(row.recipient)||'—')}</td><td class="o24-bon-phone" dir="ltr">${esc(o24BonClean(row.phone)||'—')}</td><td class="o24-bon-cod">${row.amount===null||row.amount===undefined||row.amount===''?'—':o24BonAmount(row.amount)}</td></tr>`).join('');
 let qr='';try{if(typeof o24qrSvg==='function'&&o24BonClean(data.reference))qr=o24qrSvg(data.reference,3)}catch(e){}
 const count=Number(data.count)||0,received=Number(data.received)||0,remaining=Number(data.remaining)||0;
 const status=o24BonClean(data.status),route=o24BonClean(data.route),reference=o24BonClean(data.reference)||'—';
 const signatures=(data.signatures||['Préparé par','Transporteur','Réception par le destinataire']).map(o24BonClean).filter(Boolean);
 const nature=o24BonClean(data.nature).toUpperCase(),natureNote=o24BonClean(data.nature_note);
 const natureColor={'RÉCEPTION':'#0c274c','RETOUR':'#b3261e','RAMASSAGE':'#f58024'}[nature]||'#0c274c';
 return `<style>
 @page{size:A4 portrait;margin:13mm}
 .o24-bon-print{font:10.5px/1.45 Arial,Helvetica,sans-serif;color:#172d49;width:100%;max-width:184mm}
 .o24-bon-print *{box-sizing:border-box}
 .o24-bon-header{display:grid;grid-template-columns:minmax(0,1fr) 72px minmax(0,1fr);align-items:center;gap:13px;min-height:76px;padding-bottom:11px;border-bottom:1px solid #1a1a1a}
 .o24-bon-logo img{display:block;width:145px;max-height:52px;object-fit:contain;object-position:left center}
 .o24-bon-qr{width:72px;height:72px;display:grid;place-items:center}.o24-bon-qr svg{display:block;width:72px;height:72px}
 .o24-bon-company{text-align:right;display:grid;gap:2px;font-size:10.5px;line-height:1.35;overflow-wrap:anywhere}.o24-bon-company strong{font-size:12px}
 .o24-bon-nature{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin:10px 0 0;padding:9px 14px;border-radius:6px;color:#fff;background:${natureColor}}
 .o24-bon-nature b{font-size:26px;letter-spacing:.06em;line-height:1}
 .o24-bon-nature span{font-size:10px;opacity:.92}
 .o24-bon-title{margin:12px 0 0;padding-bottom:7px;border-bottom:1.5px solid #171717;display:flex;align-items:end;justify-content:space-between;gap:12px}
 .o24-bon-title h1{font-size:21px;line-height:1.2;font-weight:400;margin:0}
 .o24-bon-title small{font-size:9px;text-align:right;color:#53657d}
 .o24-bon-route{font-size:10px;color:#53657d;margin:5px 0 0;overflow-wrap:anywhere}
 .o24-bon-meta{display:grid;grid-template-columns:minmax(130px,.8fr) minmax(190px,1fr);gap:20px;align-items:start;padding:13px 0 15px;border-bottom:1px solid #171717;min-height:78px}
 .o24-bon-date{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;font-size:11px}.o24-bon-date b{font-weight:400}
 .o24-bon-party{justify-self:center;width:100%;max-width:310px;display:grid;gap:2px;font-size:10.5px;overflow-wrap:anywhere}
 .o24-bon-party-label{font-size:8px;text-transform:uppercase;letter-spacing:.07em;color:#687992}
 .o24-bon-party strong{font-size:11.5px;color:#142b49}
 .o24-bon-count{text-align:right;margin:35px 0 0;font-size:11px;color:#344861}.o24-bon-count b{font-weight:400;margin-left:20px}
 .o24-bon-table{width:100%;table-layout:fixed;border-collapse:collapse;margin-top:42px;font-size:8.7px}
 .o24-bon-table col:nth-child(1){width:34%}.o24-bon-table col:nth-child(2){width:19%}.o24-bon-table col:nth-child(3){width:19%}.o24-bon-table col:nth-child(4){width:17%}.o24-bon-table col:nth-child(5){width:11%}
 .o24-bon-table thead{display:table-header-group}.o24-bon-table th{text-align:left;font-weight:400;border-bottom:1px solid #171717;padding:7px 4px}
 .o24-bon-table td{border-bottom:1px solid #aab3bf;padding:7px 4px;vertical-align:top;overflow-wrap:anywhere}
 .o24-bon-table tr{break-inside:avoid;page-break-inside:avoid}.o24-bon-track{font-size:8.2px;word-break:break-all}.o24-bon-phone{white-space:nowrap}.o24-bon-cod{text-align:right;white-space:nowrap}
 .o24-bon-progress{font-size:9px;color:#53657d;text-align:right;margin-top:6px}
 .o24-bon-note{font-size:9px;margin:12px 0 0;padding:7px 9px;background:#f5f7fa;border-left:2px solid #314c6d;overflow-wrap:anywhere}
 .o24-bon-signatures{display:grid;grid-template-columns:repeat(${Math.max(1,Math.min(3,signatures.length))},minmax(0,1fr));gap:18px;margin-top:25px;break-inside:avoid;page-break-inside:avoid}
 .o24-bon-sign{min-height:45px;border-top:1px solid #9ba8b7;padding-top:5px;font-size:8.5px}
 .o24-bon-footer{font-size:7.5px;line-height:1.4;color:#697990;border-top:1px solid #d5dce5;padding-top:6px;margin-top:12px}
 @media print{.o24-bon-print{max-width:none}.o24-bon-table thead{display:table-header-group}}
 @media(max-width:600px){.o24-bon-header{grid-template-columns:1fr 54px 1fr;gap:6px}.o24-bon-logo img{width:100%;max-width:115px}.o24-bon-qr,.o24-bon-qr svg{width:54px;height:54px}.o24-bon-company{font-size:8px}.o24-bon-company strong{font-size:9px}.o24-bon-meta{grid-template-columns:1fr 1.2fr;gap:8px}.o24-bon-table{font-size:7px}.o24-bon-table th,.o24-bon-table td{padding:5px 2px}}
 </style>
 <article class="o24-bon-print">
  <header class="o24-bon-header"><div class="o24-bon-logo"><img src="/static/wordmark.png" alt="ORIENTAL24"></div><div class="o24-bon-qr">${qr}</div><div class="o24-bon-company"><strong>${esc(company)}</strong>${contact.map(value=>`<span>${esc(value)}</span>`).join('')}</div></header>
  ${nature?`<div class="o24-bon-nature"><b>${esc(nature)}</b>${natureNote?`<span>${esc(natureNote)}</span>`:''}</div>`:''}
  <div class="o24-bon-title"><h1>${esc(o24BonClean(data.title)||'Bon logistique')}</h1><small>${esc(status)}</small></div>
  ${route?`<p class="o24-bon-route">${esc(route)}</p>`:''}
  <section class="o24-bon-meta"><div class="o24-bon-date"><span>Date :</span><b>${esc(o24BonClean(data.date)||'—')}</b></div><div class="o24-bon-party"><span class="o24-bon-party-label">${esc(o24BonClean(party.label)||'Destinataire')}</span><strong>${esc(o24BonClean(party.name)||'—')}</strong>${partyLines.map(line=>`<span>${esc(line)}</span>`).join('')}</div></section>
  <p class="o24-bon-count">Nombre de colis : <b>${count}</b></p>
  <table class="o24-bon-table"><colgroup><col><col><col><col><col></colgroup><thead><tr><th>ID de suivi</th><th>Ville</th><th>Nom</th><th>Téléphone</th><th>COD (MAD)</th></tr></thead><tbody>${rows||'<tr><td colspan="5">Aucun colis dans ce bon.</td></tr>'}</tbody></table>
  ${data.received!==undefined||data.remaining!==undefined?`<p class="o24-bon-progress">${received} reçu(s)${remaining?` · ${remaining} restant(s)`:''}${Number(data.missing)?` · ${Number(data.missing)} non réceptionné(s)`:''}</p>`:''}
  ${o24BonClean(data.note)?`<p class="o24-bon-note"><b>Observation :</b> ${esc(o24BonClean(data.note))}</p>`:''}
  ${signatures.length?`<section class="o24-bon-signatures">${signatures.map(label=>`<div class="o24-bon-sign">${esc(label)}</div>`).join('')}</section>`:''}
  <footer class="o24-bon-footer">Document logistique · Le COD est informatif : ce bon n’est ni une facture ni une preuve d’encaissement. Édité le ${esc(o24BonClean(data.issued)|| (typeof opsDate==='function'?opsDate(new Date().toISOString()):new Date().toLocaleDateString('fr-FR')))} · ${esc(reference)}</footer>
 </article>`;
}
function o24BonAmount(value){
 const number=Number(value);
 if(!Number.isFinite(number))return '—';
 return number.toLocaleString(typeof uiLocale==='function'?uiLocale():'fr-FR',{minimumFractionDigits:0,maximumFractionDigits:2});
}
