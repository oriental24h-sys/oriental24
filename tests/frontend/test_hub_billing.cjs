const fs=require('fs'),vm=require('vm'),assert=require('assert');
const data={rows:[],hubs:[{id:10,name:'Hub A',active:1,revision:1,mode:'gross',delivered_cents:1000,returned_cents:400,refused_cents:300,city_mode:true,cities:[{id:11,name:'Ville A',revision:1,delivered_cents:1000,returned_cents:400,refused_cents:300},{id:12,name:'Ville B',revision:0}]},{id:20,name:'Hub B',active:1,revision:1,mode:'net',cities:[]}],schedule:{enabled:0,time:'23:59',revision:0},scheduler_running:false,last_automatic_result:{count:1,missing_terms:[{name:'Hub B'}],unassigned_count:2,missing_city_terms:[{hub_name:'Hub A',city:'Ville C'}]}};
let lastModal='',lastBind=null,lastRequest=null,apiCalls=[];
const ctx=vm.createContext({URLSearchParams,setInterval:()=>{},document:{addEventListener:()=>{}},listPageSize:()=>10,O24_PAGE_SIZES:[10,25],navigate:async()=>{},S:{user:{id:2,role:'agent'}},
 api:async (path,method,body)=>{apiCalls.push({path,method,body});if(method==='PUT'&&path.startsWith('/hub-billing/terms/'))lastRequest={path,method,body};if(method==='POST'&&path==='/hub-billing/generate')lastRequest={path,method,body};if(path.startsWith('/hub-billing/preview'))return{cutoff:'2026-01-02T23:00:00+00:00',snapshot:'snapshot-hub',hubs:[{hub_id:20,hub_name:'Hub B',parcel_count:2,cod_cents:4000,commission_cents:300}],missing_terms:[],missing_city_terms:[],unassigned_count:0};return path.startsWith('/billing?')?{kind:'livreur',page:1,size:10,count:1,parties:[],totals:{cod_cents:10000,fees_cents:1000,incoming_cents:10000,outgoing_cents:1000},rows:[{id:1,reference:'DRV-1',kind:'livreur',name:'Driver',state:'Not Paid',cod_cents:10000,fees_cents:1000,net_cents:9000,incoming_cents:10000,outgoing_cents:1000,created_at:'2026-01-01',updated_at:'2026-01-01',parcel_count:1}]}:path==='/hub-billing'?data:path==='/logistics/hub/driver-statements'?{rows:[{id:1,reference:'DRV-1',driver_name:'Driver',parcel_count:1,cod_cents:10000,commission_cents:1000,status:'À régler'}]}:{rows:[]}},
 heading:(a,b)=>a+b,icon:()=>'',esc:String,centMoney:v=>String(v/100),centInput:v=>String(v/100),date:String,opsTag:String,
 stat:(...args)=>args.join(' '),simpleTable:(heads,rows)=>heads.join(' ')+rows.flat().join(' '),empty:(...a)=>a.join(' '),
 select:()=>'<select name="mode"></select>',input:(name,title,value)=>`<input name="${name}" value="${value}">${title}`,form:s=>s,
 modal:(title,html,wide)=>{lastModal=title+html;ctx.modalWide=wide},bindForm:fn=>{lastBind=fn},saved:async()=>{},financeKey:()=> 'manual-hub-123456789012345',toast:()=>{},renderView:()=>{},hubInvoicesAdminView:()=>'<legacy>'});
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
 await run('hubBillEditTerms(10)');assert(lastModal.includes('Ville A'));assert(lastModal.includes('Ville B'));assert(lastModal.includes('city_11_delivered'));assert(lastModal.includes('city_12_refused'));assert(lastModal.includes('Un tarif pour chacune des 2 villes'));assert.equal(ctx.modalWide,true);await lastBind({mode:'net',city_11_delivered:'10',city_11_returned:'4',city_11_refused:'3',city_12_delivered:'25',city_12_returned:'8',city_12_refused:'7'});assert.equal(lastRequest.body.cities.length,2);assert.equal(lastRequest.body.cities[1].city_id,12);assert.equal(lastRequest.body.mode,'net');
 await run('hubBillGeneratePreview()');assert(lastModal.includes('Tous les Hubs'));assert(lastModal.includes('Un seul Hub · Hub B'));await lastBind({hub_id:'20'});assert(apiCalls.some(x=>x.path==='/hub-billing/preview?hub_id=20'));assert(lastModal.includes('Génération manuelle · Hub B'));assert(lastModal.includes('Émettre 1 facture'));await lastBind();assert.equal(lastRequest.path,'/hub-billing/generate');assert.equal(lastRequest.body.hub_id,20);assert.equal(lastRequest.body.snapshot,'snapshot-hub');
 run("hubBillTab='schedule'");html=await run('hubBillingWorkspace()');assert(html.includes('type="time"'));assert(html.includes('Africa/Casablanca'));assert(html.includes('Hub B'));assert(html.includes('Ville C'));
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
 console.log('PASS: Hub invoice tabs, city rates, targeted manual generation, schedule, driver details and legacy access');
})().catch(e=>{console.error(e);process.exitCode=1});
