const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const palette=fs.readFileSync('static/palette-scan.js','utf8');
const helper=palette.slice(palette.indexOf('function ppReceptionSignal'),palette.indexOf('function ppSoundToggle'));
function setup(role){
 const nodes=new Map(),signals=[],messages=[];
 const node=key=>{if(!nodes.has(key))nodes.set(key,{innerHTML:'',textContent:'',value:'',isConnected:true,disabled:false,handlers:{},focus(){},addEventListener(k,f){this.handlers[k]=f},querySelector(k){return node(key+' '+k)}});return nodes.get(key)};
 const root=node('root');root.querySelector=k=>node(k);const body=node('.modal-body');body.querySelector=()=>null;
 const ctx={S:{user:{id:1,role}},ppSound:true,ppReceptionSignal:k=>signals.push(k),ppUnlockSound(){},ppBeep(){},ppRxFlash(){},ppRxMsg:(k,t)=>messages.push([k,t]),ppBadge:s=>s,esc:s=>String(s||''),icon:()=>'',modalCleanup:null,
 ppContext:()=>({node:root,current:()=>true}),ppError:(c,e)=>{throw e},ppRxCamWidget:async()=>'<button></button>',ppRxCam:(box,btn,state,cb)=>{ctx.cameraScan=cb;return{stop(){},active:()=>false,start:async()=>true}},
 api:async()=>({id:1,reference:'PP-1',status:'En transit',client_name:'Test',count:3,lines:[{tracking:'ABC',recipient:'A',city:'Test'},{tracking:'XYZ',recipient:'B',city:'Test'},{tracking:'OLD',received_at:'2026-10-20'}]}),
 document:{getElementById:id=>node('#'+id)},console};
 vm.createContext(ctx);return {ctx,node,signals,messages};
}
(async()=>{
 // Sound codes: duplicates have a dedicated low tone, errors do not reuse it.
 const tones=[];const audio={ppSound:true,ppAc:{currentTime:0,state:'running'},window:{AudioContext:function(){}},ppTone:(...a)=>tones.push(a)};vm.createContext(audio);
 vm.runInContext(palette.slice(palette.indexOf('function ppBeep'),palette.indexOf('function ppVib')),audio);
 audio.ppBeep('rx-duplicate');assert.deepEqual(tones.map(x=>x[0]),[180,130]);tones.length=0;
 audio.ppBeep('rx-error');assert.deepEqual(tones.map(x=>x[0]),[520,520,520]);tones.length=0;
 audio.ppSound=false;audio.ppBeep('rx-duplicate');assert.equal(tones.length,0);
 assert(palette.includes("return openReceptionCollection('partner',id)"));
 console.log('Partner entry delegates to unified scan collection PASS');
 // The single-scan reception path uses the server's already_received flag.
 const feedback={ppBeep:k=>feedback.sounds.push(k),ppVib(){},ppUnlockSound(){},sounds:[]};vm.createContext(feedback);vm.runInContext(helper,feedback);
 await feedback.ppReceiveWithFeedback(async()=>({already_received:false}));assert.equal(feedback.sounds.at(-1),'ok');
 await feedback.ppReceiveWithFeedback(async()=>({already_received:true}));assert.equal(feedback.sounds.at(-1),'rx-duplicate');
 await assert.rejects(()=>feedback.ppReceiveWithFeedback(async()=>{throw Error('wrong tracking')}));assert.equal(feedback.sounds.at(-1),'rx-error');
 const n=feedback.sounds.length;await feedback.ppReceiveWithFeedback(async()=>({}),()=>false);assert.equal(feedback.sounds.length,n);

 assert(fs.readFileSync('static/ramassage-bon.js','utf8').includes('return rbCollectReceive(id)'));
 console.log('Ramassage reception delegates to collected-scan interface PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
