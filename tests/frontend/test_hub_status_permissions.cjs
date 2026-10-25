const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('static/parcel-state.js','utf8');
const helper=source.split('\n').find(l=>l.startsWith('function hubParcelStatusEditable('));
const ctx=vm.createContext({S:{user:{role:'agent'}}});vm.runInContext(helper,ctx);
function editable(p){ctx.p=p;return vm.runInContext('hubParcelStatusEditable(p)',ctx)}
for(const status of ['Réceptionné','Reçu par le livreur','En livraison','Reporté','Retourné','Refusé'])assert(editable({status,hub_status_editable:true}));
assert(!editable({status:'Livré',hub_status_editable:true}));
assert(!editable({status:'Reporté',hub_status_editable:false}));
for(const lock of ['invoice_id','financial_locked','operations_locked'])assert(!editable({status:'Reporté',hub_status_editable:true,[lock]:1}));
ctx.S.user.role='client';assert(!editable({status:'Reporté',hub_status_editable:true}));
console.log('PASS: own Hub capability, courier statuses, returned editable, delivered locked, financial/document locks');
