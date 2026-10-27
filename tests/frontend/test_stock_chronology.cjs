const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('static/parcel-contacts.js','utf8');
const ctx=vm.createContext({S:{user:{role:'support'}},opsOffline:false,
  esc:v=>String(v??''),money:String,opsDate:String,icon:()=>'',tag:s=>`<status>${s}</status>`,
  parcelCopyButton:()=>'',parcelPhone:()=>'',riskPanel:()=>'',parcelPolicyBadges:()=>'',parcelContactCard:()=>'',parcelNoteControl:()=>''});
vm.runInContext(source.slice(source.indexOf('function parcelCommandBody('),source.indexOf('async function loadParcelCommand(')),ctx);
const when='2026-10-27T16:59:00';
const events=[
 {id:3,status:'Réceptionné',created_at:'2026-10-27T17:13:00'},
 {id:2,status:'Transit',created_at:'2026-10-27T17:09:00'},
 {id:1,status:'Ramassé',created_at:when},
 {id:null,status:'Confirmé',timeline_order:-1,created_at:when,actor:'Hub Central',history_reconstructed:true},
 {id:null,status:'Créé',timeline_order:-2,created_at:when,actor:'Client',history_reconstructed:true},
 {id:4,status:'Appel client',created_at:'2026-10-27T17:14:00'},
 {id:5,status:'WhatsApp client',created_at:'2026-10-27T17:14:00'},
];
const d={parcel:{id:1,tracking:'STOCK-1',status:'Réceptionné'},events};
const before=JSON.stringify(events);
const html=ctx.parcelCommandBody(d);
const chronology=html.slice(html.indexOf('parcel-chronology-heading'));
const expected=['Créé','Confirmé','Ramassé','Transit','Réceptionné','Appel client','WhatsApp client'];
let previous=-1;
for(const status of expected){const pos=chronology.indexOf(`<status>${status}</status>`);assert(pos>previous,status);previous=pos}
assert(chronology.includes('7 événement(s)'));
assert.equal(JSON.stringify(events),before,'Rendering must not mutate the source history');
// Ordinary events at the same second retain their original ID order.
const regular=ctx.parcelCommandBody({parcel:d.parcel,events:[{id:2,status:'WhatsApp client',created_at:when},{id:1,status:'Appel client',created_at:when}]}).split('parcel-chronology-heading')[1];
assert(regular.indexOf('<status>Appel client</status>')<regular.indexOf('<status>WhatsApp client</status>'));
console.log('PASS: initial stock stages precede pickup at equal timestamps; later transit/receipt/contact history and source array preserved');
