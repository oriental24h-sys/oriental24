const fs=require('fs'),vm=require('vm'),assert=require('assert');
const app=fs.readFileSync('static/app.js','utf8');
const source=app.slice(app.indexOf('function newParcel() {'),app.indexOf('async function parcelDetail('));
let modalTitle='',modalBody='',closed=0,stockFlow=0,regularSubmit=null;
const ctx=vm.createContext({
 S:{user:{role:'client'},cities:[{id:1,delivery:1,fee:20}],users:[]},opsOffline:false,
 modal:(title,body)=>{modalTitle=title;modalBody=body},closeModal:()=>closed++,newFulfillment:()=>stockFlow++,
 icon:()=>'',form:x=>x,select:(name,label)=>`<select name="${name}">${label||''}</select>`,
 clientOptions:()=>[],clientTrackingSlot:()=>'<div id="client-tracking-slot"></div>',
 input:(name,label)=>`<input name="${name}" aria-label="${label}">`,textarea:(name,label)=>`<textarea name="${name}">${label}</textarea>`,
 money:String,bindClientTracking:()=>{},bindForm:fn=>{regularSubmit=fn},
});
vm.runInContext(source,ctx);
ctx.newParcel();
assert.equal(modalTitle,'Mode de création de la CMD');
assert(modalBody.includes('newParcelFromStock()'));assert(modalBody.includes('newParcelRegular()'));
assert(modalBody.includes('réservées immédiatement'));assert(modalBody.includes('CMD classique ne touche pas au stock'));
ctx.newParcelFromStock();assert.equal(closed,1);assert.equal(stockFlow,1);
ctx.newParcelRegular();assert.equal(modalTitle,'Nouveau colis');assert(modalBody.includes('Nature du produit'));
ctx.opsOffline=true;ctx.newParcel();assert.equal(modalTitle,'Nouveau colis');
console.log('PASS: new CMD offers stock-linked vs classic; stock routes to reservation flow; offline demo preserves classic CMD');
