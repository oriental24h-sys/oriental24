const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('static/parcel-state.js','utf8');
const fn=src.slice(src.indexOf('async function selectParcelStatus('),src.indexOf('async function submitParcelStatus('));
const node={innerHTML:'',querySelector:()=>({focus(){}})};
const ctx=vm.createContext({S:{user:{role:'livreur'},status_policy:{attempt_sources:['En livraison'],attempt_outcomes:['Livré'],help:{},rank:{}}},opsOffline:false,
 activeReasonMenu:null,statusMenuHeader:()=>'<header></header>',financeKey:()=> 'key',money:String,esc:String,icon:()=>'',statusMenuError:(_,e)=>{throw e}});
vm.runInContext(fn,ctx);
(async()=>{
 for(const otp_required of [false,true]){
  const state={node,parcel:{status:'En livraison',amount:125.5,otp_required},place(){}};
  ctx.activeReasonMenu=state;ctx.state=state;
  await vm.runInContext("selectParcelStatus(state,'Livré')",ctx);
  assert(state.attempt);assert(node.innerHTML.includes('Confirmer Livré'));
  for(const field of ['receiver','collected_amount','note'])assert(!node.innerHTML.includes(`name="${field}"`),field);
  assert.equal(node.innerHTML.includes('name="otp"'),otp_required);
 }
 console.log('PASS: delivery confirmation without receiver/COD/comment fields; optional OTP preserved');
})().catch(e=>{console.error(e);process.exitCode=1});
