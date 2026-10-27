const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('static/app.js','utf8');
const ctx=vm.createContext({S:{user:{role:'agent',agent_hub_id:20},hubs:[{id:20,name:'NV BERKAN'}],users:[{id:7,role:'livreur',driver_hub_id:20}]},view:'print',
 esc:v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),
 date:()=>'',money:String,initials:()=>'',icon:()=>'',tag:String,
 parcelPolicyBadges:()=>'',returnStateTag:()=>'',codChip:()=>''});
vm.runInContext(src.slice(src.indexOf('function parcelAtHubLabel('),src.indexOf('function parcelsView(')),ctx);
const base={id:1,tracking:'RECEIVED-1',recipient:'Recipient',city:'Berkane',phone:'0612345678',status:'Réceptionné',amount:100,company:'Client',driver_id:null,driver:null,current_hub_id:20,current_hub_name:'NV BERKAN'};
let html=ctx.parcelTable([base],false);
assert(html.includes('Au Hub — NV BERKAN'));
assert(!html.includes('Non affecté'));assert(!html.includes('Aucun livreur local'));
assert(ctx.parcelAgencyCell(base).includes('Au Hub — NV BERKAN'));
// The source Hub's tracking view must show the receiving Hub, not its own Hub.
ctx.S.user.agent_hub_id=10;ctx.S.hubs=[{id:10,name:'Hub Central'}];
html=ctx.parcelTable([base],false);assert(html.includes('Au Hub — NV BERKAN'));assert(!html.includes('Au Hub — Hub Central'));
// Still show the driver after local assignment.
ctx.S.user.agent_hub_id=20;
html=ctx.parcelTable([{...base,driver_id:7,driver:'Youssef'}],false);
assert(html.includes('Youssef'));assert(html.includes('Affectation locale'));assert(!html.includes('Au Hub —'));
// Never confuse a parcel in transit with physical receipt.
const transit={...base,current_hub_id:null,current_hub_name:null,status:'Transit',transit_direction:'destination',transit_destination:'NV BERKAN'};
assert(!ctx.parcelTable([transit],false).includes('Au Hub —'));
assert(ctx.parcelAgencyCell(transit).includes('Transit vers ville de destination'));
// Preserve the returned-courier indicator and escape the Hub name.
html=ctx.parcelTable([{...base,driver_id:7,driver_returned:1}],false);
assert(html.includes('Au Hub — NV BERKAN'));assert(html.includes('Récupéré du livreur'));
html=ctx.parcelTable([{...base,current_hub_name:'<Hub X>'}],false);
assert(html.includes('Au Hub — &lt;Hub X&gt;'));assert(!html.includes('<Hub X>'));
ctx.S.user.role='admin';html=ctx.parcelTable([base],false);assert(html.includes('Au Hub — NV BERKAN'));
console.log('PASS: received/unassigned parcels show actual Hub name, sender tracking uses destination name, assigned drivers and transit remain distinct');
