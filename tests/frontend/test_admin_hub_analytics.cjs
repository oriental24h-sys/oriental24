const fs=require('fs'),vm=require('vm'),assert=require('assert');
const rows=[{id:10,name:'Hub A',active:1,assigned:2,processed:1,pending:1,delivered:1,returned:0,progress:50,delivery_rate:50,return_rate:0,risk:false,daily:{'2026-01-01':2},worked_days:1,never_worked:false},{id:20,name:'Hub vide',active:1,assigned:0,processed:0,pending:0,delivered:0,returned:0,progress:0,delivery_rate:0,return_rate:0,risk:false,daily:{'2026-01-01':0},worked_days:0,never_worked:true}];
const data={hubs:rows.map(({id,name,active})=>({id,name,active})),hub:{id:null,name:'Tous les Hubs'},rows,days:['2026-01-01'],summary:{hubs:2,active_hubs:2,assigned:2,processed:1,pending:1,delivered:1,risk:0,progress:50,delivery_rate:50,days:1,average_hubs:1,inactive_hub_days:1,never_worked:1},parcels:[{hub_id:10,tracking:'HUB-PENDING',assigned_at:'2026-01-01T10:00',assigned_day:'2026-01-01',outcome:'Sans tentative',processed:false},{hub_id:10,tracking:'HUB-DONE',assigned_at:'2026-01-01T10:00',assigned_day:'2026-01-01',outcome:'Livré',evidence_source:'attempt',processed:true}]};
let modal='',download='',csv='';
const ctx=vm.createContext({menu:[],titles:{},S:{user:{id:1,role:'admin'}},URLSearchParams,Intl,Date,
api:async path=>{assert(path.startsWith('/admin-hub-analytics?'));assert(!path.includes('driver_id'));return data},esc:String,renderView:()=>{},
modal:(t,h)=>{modal=t+h},simpleTable:(a,b)=>a.join(' ')+b.flat().join(' '),empty:(...a)=>a.join(' '),
billingCSV:t=>{csv=JSON.stringify(t);return csv},Blob,billingSaveFile:(b,n)=>{download=n},toast:e=>{throw Error(e)}});
const manager=fs.readFileSync('static/hub-manager-analytics.js','utf8');
vm.runInContext(manager,ctx);vm.runInContext(fs.readFileSync('static/admin-hub-analytics.js','utf8'),ctx);
const run=s=>vm.runInContext(s,ctx);
(async()=>{
assert.equal(run("menu.find(x=>x[1][0][0]==='admin-hub-analytics')[1][0][3][0]"),'admin');
assert.equal(run("menu.find(x=>x[1][0][0]==='hub-manager-analytics')[1][0][3][0]"),'agent');
let html=await run('adminHubAnalyticsView()');
for(const text of ['Activité générale','Analyse des Hubs','Activité quotidienne des Hubs','Tous les Hubs','Hub A','ha-subnav','ha-ring'])assert(html.includes(text),text);
assert(html.includes('name="hub_id"'));assert(!html.includes('name="driver_id"'));
run("ahaTab='drivers'");html=await run('adminHubAnalyticsView()');assert(html.includes('Taux de livraison'));assert(html.includes('Hub actif'));assert(html.includes('ha-person-stats'));
run("ahaLayout='table'");html=await run('adminHubAnalyticsView()');assert(html.includes('ha-table'));assert(!html.includes('ha-person-stats'));
run('ahaDetail(10,true)');assert(modal.includes('HUB-PENDING'));assert(!modal.includes('HUB-DONE'));
run("ahaTab='daily'");html=await run('adminHubAnalyticsView()');assert(html.includes('Matrice Hubs × jours'));assert(html.includes('data-heat='));assert(html.includes('Jours-Hubs inactifs'));
run("ahaDay(10,'2026-01-01')");assert(modal.includes('HUB-DONE'));assert(modal.includes('HUB-PENDING'));
run("ahaDay(20,'2026-01-01')");assert(!modal.includes('HUB-DONE'));
run("ahaDailyLayout='table';ahaNever=true");html=await run('adminHubAnalyticsView()');assert(html.includes('Activité quotidienne · liste'));assert(!html.includes('Hub A</td>'));
assert.equal(run('ahaRows().length'),1);run('ahaExport()');assert.equal(download,'ORIENTAL24-analytique-admin-daily.csv');assert(csv.includes('Hub vide'));assert(!csv.includes('Hub A'));
run("ahaNever=false;ahaRisk=true");assert.equal(run('ahaRows().length'),0);
run("ahaRisk=false;ahaTab='hub';ahaExport()");assert(csv.includes('Tous les Hubs'));
assert.equal(run('hmaOwner'),null);assert.equal(run('hmaTab'),'hub');
console.log('PASS: Admin Hub-only navigation, global/cards/list/daily views, filters, drilldowns, CSV and manager state isolation');
})().catch(e=>{console.error(e);process.exitCode=1});
