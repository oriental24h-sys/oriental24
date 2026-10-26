const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('static/billing.js','utf8');
const apply=src.slice(src.indexOf('async function billingApply('),src.indexOf('\nasync function billingPage('));
let captured='',toastError='';
const ctx=vm.createContext({
 S:{user:{id:77,role:'admin'}},billingOwner:77,
 billingFilters:{kind:'client',archive:'all',state:'',party:'',q:'',from:'',to:'',page:4,size:20},
 URLSearchParams,listPageSize:()=>20,toast:(m,error)=>{if(error)toastError=m},
 renderView:async()=>{captured=new URLSearchParams(ctx.billingFilters).toString()},
});
vm.runInContext(apply,ctx);
const fields={from:'2026-01-01T00:00',to:'2026-01-02T23:59',state:'Paid',party:'42',q:'FAC-1042'};
const button={disabled:false,isConnected:true};
const form={querySelector:()=>button,elements:{namedItem:name=>({value:fields[name]})}};
(async()=>{
 let prevented=false;
 await ctx.billingApply({preventDefault(){prevented=true},currentTarget:form,target:form});
 assert(prevented);assert.equal(button.disabled,false);assert.equal(toastError,'');
 const q=new URLSearchParams(captured);
 for(const [key,value] of Object.entries(fields))assert.equal(q.get(key),value,key);
 assert.equal(q.get('page'),'1');assert.equal(q.get('kind'),'client');
 fields.from='2026-01-03T00:00';fields.to='2026-01-02T00:00';captured='';
 await ctx.billingApply({preventDefault(){},currentTarget:form,target:form});
 assert(toastError.includes('précéder'));assert.equal(captured,'');
 console.log('PASS: billing form transmits date, state, client and search filters together; validates range and resets page');
})().catch(e=>{console.error(e);process.exitCode=1});
