const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Button {
 constructor(key,label){this.dataset={nav:key};this.label=label;this.badges=[];this.attrs={};}
 querySelectorAll(){return [...this.badges];}
 querySelector(){return {textContent:this.label};}
 setAttribute(k,v){this.attrs[k]=v;}
 appendChild(b){this.badges.push(b);b.remove=()=>{this.badges=this.badges.filter(x=>x!==b)};}
}
const buttons=[new Button('partner-palettes','Palettes partenaires'),new Button('palette-hub','Palettes'),new Button('settings','Paramètres')];
let scheduled, payload={counts:{'partner-palettes':2,'palette-hub':0}}, interval;
const ctx=vm.createContext({S:{user:{id:1,role:'agent'},csrf:'a'},opsOffline:false,
 document:{visibilityState:'visible',querySelectorAll:()=>buttons,querySelector:()=>({}),createElement:()=>({setAttribute(){}}),addEventListener(){}},
 shell(){},api:async()=>payload,setTimeout(fn){scheduled=fn;return 1},clearTimeout(){},setInterval(fn){interval=fn},console});
vm.runInContext(fs.readFileSync('static/sidebar-counts.js','utf8'),ctx);
(async()=>{
 await scheduled();assert.equal(buttons[0].badges[0].textContent,'2');assert.equal(buttons[1].badges.length,0);
 vm.runInContext('shell()',ctx);assert.equal(buttons[0].badges[0].textContent,'2');
 await scheduled();assert.equal(buttons[0].badges[0].textContent,'2'); // visiting never clears pending work
 payload={counts:{'partner-palettes':1}};
 await vm.runInContext("api('/partner-palettes/1/receive','POST',{})",ctx);await scheduled();
 assert.equal(buttons[0].badges[0].textContent,'1');assert(buttons[0].attrs['aria-label'].includes('1 à traiter'));
 payload={counts:{'partner-palettes':0}};interval();await new Promise(setImmediate);assert.equal(buttons[0].badges.length,0);
 payload={counts:{'partner-palettes':2}};interval();await new Promise(setImmediate);
 vm.runInContext("S={user:{id:2,role:'client'},csrf:'b'};shell()",ctx);
 assert.equal(buttons[0].badges.length,0); // no badge leak on account switch
 console.log('PASS: 2→1→0, navigation preserves count, writes/poll refresh, zero hidden, accessible labels, account isolation');
})().catch(e=>{console.error(e);process.exitCode=1});
