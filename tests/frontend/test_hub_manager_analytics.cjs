const fs=require('fs'),vm=require('vm'),assert=require('assert');
const rows=[{id:1,name:'Local Driver',active:1,assigned:2,processed:1,pending:1,delivered:0,returned:0,progress:50,delivery_rate:0,return_rate:0,risk:false,daily:{'2026-01-01':2},worked_days:1,never_worked:false},{id:2,name:'No assignments',active:1,assigned:0,processed:0,pending:0,delivered:0,returned:0,progress:0,delivery_rate:0,return_rate:0,risk:false,daily:{'2026-01-01':0},worked_days:0,never_worked:true}];
const data={hub:{id:10,name:'Hub A'},rows,days:['2026-01-01'],summary:{drivers:2,active_drivers:2,assigned:2,processed:1,pending:1,delivered:0,risk:0,progress:50,delivery_rate:0,days:1,average_drivers:1,inactive_driver_days:1,never_worked:1},parcels:[{driver_id:1,tracking:'LOCAL-TEST',assigned_at:'2026-01-01',outcome:'Sans tentative',processed:false}]};
let modal='',download=null;
const ctx=vm.createContext({menu:[],titles:{},S:{user:{id:7,role:'agent',agent_hub_id:10}},URLSearchParams,Intl,Date,
 api:async path=>{assert(path.startsWith('/hub-manager-analytics?'));assert(!path.includes('hub_id='));return data},
 heading:(...a)=>a.join(' '),esc:String,icon:()=>'',stat:(...a)=>a.join(' '),simpleTable:(a,b)=>a.join(' ')+b.flat().join(' '),empty:(...a)=>a.join(' '),renderView:()=>{},
 modal:(title,html)=>{modal=title+html},billingCSV:JSON.stringify,Blob, billingSaveFile:(blob,name)=>{download=name},toast:e=>{throw Error(e)}});
vm.runInContext(fs.readFileSync('static/hub-manager-analytics.js','utf8'),ctx);
const run=s=>vm.runInContext(s,ctx);
(async()=>{
 let html=await run('hubManagerAnalyticsView()');for(const label of ['Activité du Hub','Analyse des livreurs','Activité quotidienne','Hub A','Progression globale'])assert(html.includes(label));
 run("hmaTab='drivers'");html=await run('hubManagerAnalyticsView()');assert(html.includes('Local Driver'));assert(html.includes('En attente'));
 run('hmaRisk=true');assert.equal(run('hmaRows().length'),0);run("hmaRisk=false;hmaTab='daily'");html=await run('hubManagerAnalyticsView()');assert(html.includes('Matrice livreurs'));assert(html.includes("hmaDay(1,'2026-01-01')"));
 run('hmaNever=true');assert.equal(run('hmaRows().length'),1);run('hmaExport()');assert.equal(download,'ORIENTAL24-analytique-daily.csv');
 run('hmaDetail(1,true)');assert(modal.includes('LOCAL-TEST'));
 console.log('PASS: manager analytics navigation, Hub/cards/daily views, risk/never filters, drilldown and CSV');
})().catch(e=>{console.error(e);process.exitCode=1});
