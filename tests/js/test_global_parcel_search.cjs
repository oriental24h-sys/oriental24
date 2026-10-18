const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const s=fs.readFileSync('static/app.js','utf8'),ctx={};vm.createContext(ctx);
vm.runInContext(s.slice(s.indexOf('function globalParcelMatches('),s.indexOf('async function runGlobalParcelSearch(')),ctx);
const rows=[{id:1,tracking:'ABC-123-X',recipient:'Émilie',phone:'06 12 34 56 78',status:'Retourné'},{id:2,tracking:'ABC-123',recipient:'Amine',phone:'0600000000',status:'Livré'}];
const ids=q=>Array.from(ctx.globalParcelMatches(rows,q),p=>p.id);
assert.deepEqual(ids('abc-123'),[2,1]);assert.deepEqual(ids('emilie'),[1]);assert.deepEqual(ids('0612345678'),[1]);assert.deepEqual(ids(''),[]);assert.deepEqual(ids('foreign-code'),[]);
console.log('Global parcel search matching PASS');
