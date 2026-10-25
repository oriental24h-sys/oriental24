const fs=require('fs'),vm=require('vm'),assert=require('assert');
const data={rows:[],hubs:[{id:10,name:'Hub A',active:1,revision:1,mode:'gross',delivered_cents:1000,returned_cents:400,refused_cents:300}],schedule:{enabled:0,time:'23:59',revision:0},scheduler_running:false,last_automatic_result:{count:1,missing_terms:[{name:'Hub B'}],unassigned_count:2}};
let lastModal='';
const ctx=vm.createContext({S:{user:{id:2,role:'agent'}},
 api:async path=>path==='/hub-billing'?data:path==='/logistics/hub/driver-statements'?{rows:[{id:1,reference:'DRV-1',driver_name:'Driver',parcel_count:1,cod_cents:10000,commission_cents:1000,status:'À régler'}]}:{rows:[]},
 heading:(a,b)=>a+b,icon:()=>'',esc:String,centMoney:v=>String(v/100),centInput:v=>String(v/100),date:String,opsTag:String,
 stat:(...args)=>args.join(' '),simpleTable:(heads,rows)=>heads.join(' ')+rows.flat().join(' '),empty:(...a)=>a.join(' '),
 select:()=>'<select name="mode"></select>',input:(name,title,value)=>`<input name="${name}" value="${value}">${title}`,form:s=>s,
 modal:(title,html)=>{lastModal=title+html},bindForm:()=>{},renderView:()=>{},hubInvoicesAdminView:()=>'<legacy>'});
vm.runInContext(fs.readFileSync('static/hub-billing.js','utf8'),ctx);
const run=code=>vm.runInContext(code,ctx);
(async()=>{
 let html=await run('hubBillingWorkspace()');
 assert(html.includes('Mes factures'));assert(html.includes('Factures livreurs'));
 for(const forbidden of ['Factures clients','Paiements vendeurs','Configurer le barème','Enregistrer le planning','générer maintenant'])assert(!html.includes(forbidden));
 run("hubBillTab='drivers'");html=await run('hubBillingWorkspace()');assert(html.includes('DRV-1'));assert(html.includes('openDriverStatement(1)'));
 run("S.user={id:1,role:'admin'}");html=await run('hubBillingWorkspace()');assert(html.includes('Barèmes des Hubs'));assert(html.includes('Génération automatique'));
 run("hubBillTab='terms'");html=await run('hubBillingWorkspace()');assert(html.includes('Hub A'));assert(html.includes('Configurer le barème'));
 await run('hubBillEditTerms(10)');assert(lastModal.includes('name="delivered" value="10"'));assert(lastModal.includes('name="returned"'));assert(lastModal.includes('name="refused"'));
 run("hubBillTab='schedule'");html=await run('hubBillingWorkspace()');assert(html.includes('type="time"'));assert(html.includes('Africa/Casablanca'));assert(html.includes('Hub B'));
 run("hubBillTab='legacy'");html=await run('hubBillingWorkspace()');assert(html.includes('<legacy>'));
 console.log('PASS: Hub invoice tabs, rates, configurable schedule, driver details and legacy access');
})().catch(e=>{console.error(e);process.exitCode=1});
