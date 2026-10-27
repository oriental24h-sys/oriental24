const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('static/logistics.js','utf8');
let printed='',modalHtml='',printData;
const line=(tracking,extra={})=>({tracking,recipient:'Recipient '+tracking,city:'Berkane',phone:'0612345678',amount:100,initial_status:'Réceptionné',current_status:'Transit',current_hub_id:null,departure_scanned_at:'2026-10-27T17:09:00',received_at:null,...extra});
const doc={id:28,reference:'TRF-000028',kind:'transfer',source_hub_id:10,destination_hub_id:20,source_name:'Hub Central',destination_name:'Berkane',status:'En transit',revision:3,created_at:'2026-10-27T17:09:00',dispatched_at:'2026-10-27T17:09:00',departure_scan_required:1,departure_scanned:2,count:2,received:0,lines:[line('SENT-1'),line('SENT-2')],audit:[]};
const ctx=vm.createContext({S:{user:{id:1,role:'agent',agent_hub_id:10},settings:{}},opsDoc:null,
  api:async path=>{assert.equal(path,'/logistics/documents/28');return doc},
  esc:v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),
  money:String,opsDate:String,opsKinds:{transfer:'Palette inter-hub'},opsTag:String,tag:String,icon:()=>'',opsEtaAt:()=>null,
  simpleTable:(heads,rows)=>'<table>'+rows.map(row=>'<tr>'+row.join('|')+'</tr>').join('')+'</table>',
  modal:(title,html)=>{modalHtml=html},toast:(msg,error)=>{if(error)throw Error(msg)},
  doPrint:async(html,guard)=>{guard({innerHTML:html});printed=html}
});
vm.runInContext(fs.readFileSync('static/bon-print.js','utf8'),ctx);
const actualPrintMarkup=ctx.o24BonHtml;ctx.o24BonHtml=data=>{printData=data;return actualPrintMarkup(data)};
vm.runInContext(source.slice(source.indexOf('async function openOpsDocument('),source.indexOf('function opsDocAction(')),ctx);
vm.runInContext(source.slice(source.indexOf('async function printOpsDocument('),source.indexOf('function opsSettingsView(')),ctx);
(async()=>{
  await ctx.openOpsDocument(28,true);
  for(const tracking of ['SENT-1','SENT-2'])assert(modalHtml.includes(tracking));
  await ctx.printOpsDocument(28);
  for(const text of ['Bon d’envoi','SENT-1','SENT-2','Berkane','0612345678'])assert(printed.includes(text),text);
  assert.equal(printData.rows.length,2);assert.equal(printData.count,2);assert.equal(printData.remaining,2);
  // A received shipment keeps the same manifest for printing from its source.
  doc.status='Reçu';doc.received=2;doc.lines.forEach(l=>{l.current_hub_id=20;l.received_at='2026-10-28T10:00:00';l.active=0});
  await ctx.printOpsDocument(28);assert.equal(printData.rows.length,2);assert.equal(printData.remaining,0);
  // Partial dispatch never lists parcels which did not actually leave.
  doc.status='Départ partiel';doc.received=0;doc.count=3;
  doc.lines.push(line('NOT-SENT',{departure_scanned_at:null,current_hub_id:10}));
  doc.lines.push(line('RECONCILED',{departure_scanned_at:null,current_hub_id:10,departure_reconciled_at:'2026-10-27T18:00:00'}));
  await ctx.printOpsDocument(28);
  assert.equal(printData.count,2);assert.equal(printData.rows.length,2);
  assert(!printed.includes('NOT-SENT'));assert(!printed.includes('RECONCILED'));assert(printed.includes('1 colis en attente de départ'));
  // Draft and legacy manifests remain printable.
  doc.status='Préparé';await ctx.printOpsDocument(28);assert.equal(printData.rows.length,3);
  doc.departure_scan_required=0;doc.status='En transit';await ctx.printOpsDocument(28);assert.equal(printData.rows.length,3);
  console.log('PASS: source modal and real printable Bon show sent parcels, receipt preserves history, partial dispatch excludes unsent/reconciled lines');
})().catch(e=>{console.error(e);process.exitCode=1});
