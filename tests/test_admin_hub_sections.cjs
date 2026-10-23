const fs=require('fs'),vm=require('vm'),assert=require('assert');
const app=fs.readFileSync('static/app.js','utf8'),security=fs.readFileSync('static/security.js','utf8'),contacts=fs.readFileSync('static/parcel-contacts.js','utf8');
const helper=app.slice(app.indexOf('function adminHubSectionRemoved('),app.indexOf('async function navigate(v)'));
const ctx=vm.createContext({S:{user:{role:'admin'}},opsOffline:false,profileView:()=>'<profile>',icon:()=>'',menu:[],titles:{},boot:()=>{}});
vm.runInContext(helper+'\n'+security,ctx);
for(const role of ['admin','agent','hub_manager','client','livreur','support']){
 ctx.S.user.role=role;
 for(const section of ['security','support-team'])assert.equal(vm.runInContext(`adminHubSectionRemoved('${section}')`,ctx),['admin','agent','hub_manager'].includes(role));
 assert.equal(vm.runInContext('profileView()',ctx).includes('Gérer mes sessions'),!['admin','agent','hub_manager'].includes(role));
 assert.equal(vm.runInContext("adminHubSectionRemoved('profile')",ctx),false);
}
assert(!contacts.includes("navigate('support-team')"));
assert(!contacts.includes("menu.push(['ASSISTANCE'"));
assert(app.includes('if (adminHubSectionRemoved(view)) return navigate(view)'));
assert(app.includes('!adminHubSectionRemoved(x[0], u)'));
console.log('PASS: Admin / Hub sections removed, profile links removed, other roles preserved, navigation guards present');
