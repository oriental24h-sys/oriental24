const fs=require('fs'),vm=require('vm'),assert=require('assert');
const data={rows:[],hubs:[{id:10,name:'Hub A',active:1,revision:1,mode:'gross',delivered_cents:1000,returned_cents:400,refused_cents:300}],schedule:{enabled:0,time:'23:59',revision:0},scheduler_running:false,last_automatic_result:{count:1,missing_terms:[{name:'Hub B'}],unassigned_count:2}};
let lastModal='';
const ctx=vm.createContext({URLSearchParams,setInterval:()=>{},document:{addEventListener:()=>{}},listPageSize:()=>10,O24_PAGE_SIZES:[10,25],navigate:async()=>{},S:{user:{id:2,role:'agent'}},
 api:async path=>path.startsWith('/billing?')?{kind:'livreur',page:1,size:10,count:1,parties:[],totals:{cod_cents:10000,fees_cents:1000,incoming_cents:10000,outgoing_cents:1000},rows:[{id:1,reference:'DRV-1',kind:'livreur',name:'Driver',state:'Not Paid',cod_cents:10000,fees_cents:1000,net_cents:9000,incoming_cents:10000,outgoing_cents:1000,created_at:'2026-01-01',updated_at:'2026-01-01',parcel_count:1}]}:path==='/hub-billing'?data:path==='/logistics/hub/driver-statements'?{rows:[{id:1,reference:'DRV-1',driver_name:'Driver',parcel_count:1,cod_cents:10000,commission_cents:1000,status:'À régler'}]}:{rows:[]},
 heading:(a,b)=>a+b,icon:()=>'',esc:String,centMoney:v=>String(v/100),centInput:v=>String(v/100),date:String,opsTag:String,
 stat:(...args)=>args.join(' '),simpleTable:(heads,rows)=>heads.join(' ')+rows.flat().join(' '),empty:(...a)=>a.join(' '),
 select:()=>'<select name="mode"></select>',input:(name,title,value)=>`<input name="${name}" value="${value}">${title}`,form:s=>s,
 modal:(title,html)=>{lastModal=title+html},bindForm:()=>{},renderView:()=>{},hubInvoicesAdminView:()=>'<legacy>'});
vm.runInContext(fs.readFileSync('static/hub-billing.js','utf8'),ctx);
vm.runInContext(fs.readFileSync('static/billing.js','utf8'),ctx);
const run=code=>vm.runInContext(code,ctx);
(async()=>{
 let html=await run('hubBillingWorkspace()');
 assert(html.includes('Mes factures'));assert(html.includes('Factures livreurs'));
 for(const forbidden of ['Factures clients','Paiements vendeurs','Configurer le barème','Enregistrer le planning','générer maintenant'])assert(!html.includes(forbidden));
 run("hubBillTab='drivers'");html=await run('hubBillingWorkspace()');assert(html.includes('DRV-1'));assert(html.includes("billingOpen('livreur',1)"));assert(html.includes('billing-state-select'));assert(html.includes("billingDownload('livreur',1,'pdf')"));assert(html.includes("billingDownload('livreur',1,'csv')"));assert(!html.includes('Paiements vendeurs'));assert(!html.includes('Factures clients'));
 run("S.user={id:1,role:'admin'}");html=await run('hubBillingWorkspace()');assert(html.includes('Barèmes des Hubs'));assert(html.includes('Génération automatique'));
 run("hubBillTab='terms'");html=await run('hubBillingWorkspace()');assert(html.includes('Hub A'));assert(html.includes('Configurer le barème'));
 await run('hubBillEditTerms(10)');assert(lastModal.includes('name="delivered" value="10"'));assert(lastModal.includes('name="returned"'));assert(lastModal.includes('name="refused"'));
 run("hubBillTab='schedule'");html=await run('hubBillingWorkspace()');assert(html.includes('type="time"'));assert(html.includes('Africa/Casablanca'));assert(html.includes('Hub B'));
 run("hubBillTab='legacy'");html=await run('hubBillingWorkspace()');assert(html.includes('<legacy>'));
 run("S.user={id:1,role:'admin'};billingReset('client')");
 for(const kind of ['client','livreur']){
  ctx.fixture={kind,page:1,size:10,count:0,rows:[],parties:[],totals:{cod_cents:0,fees_cents:0,incoming_cents:0,outgoing_cents:0}};
  html=run('billingView(fixture)');
  for(const label of ['Factures clients','Factures livreurs','Factures des Hubs','Paiements vendeurs'])assert(html.includes(label));
 }
 html=await run('billingHubView()');assert(html.includes('billingOpenHubs()'));assert(html.includes('Factures émises'));assert(html.includes('Génération automatique'));
 await run('billingOpenHubs()');assert.equal(run('billingPane'),'hubs');
 await run("billingSwitch('livreur')");assert.equal(run('billingPane'),'factures');assert.equal(run('billingFilters.kind'),'livreur');
 await run('billingAging()');assert.equal(run('billingPane'),'aging');
 run("S.user={id:2,role:'agent'}");assert.equal(run("billingAdminTabs('hubs')"),'');assert.equal(await run('billingHubView()'),'');
 run("S.user={id:1,role:'admin'}");
 ctx.invoice={id:9,state:'Not Paid',cash_due_cents:433200,cash_remaining_cents:433200};
 html=run('hubBillPaymentCell(invoice)');assert(html.includes('Confirmer reçu / Paid'));assert(!html.includes('Partiel'));
 run("invoice.state='Paid';invoice.cash_remaining_cents=0;invoice.paid_on='2026-10-25'");html=run('hubBillPaymentCell(invoice)');assert(!html.includes('hubBillSetPaid'));assert(html.includes('Paid'));
 run("S.user={id:2,role:'agent'};invoice.state='Not Paid'");html=run('hubBillPaymentCell(invoice)');assert(!html.includes('hubBillSetPaid'));
 console.log('PASS: Hub invoice tabs, rates, configurable schedule, driver details and legacy access');
})().catch(e=>{console.error(e);process.exitCode=1});
