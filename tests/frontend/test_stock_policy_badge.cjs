const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync('static/app.js', 'utf8');
const ctx = vm.createContext({});
vm.runInContext(source.slice(source.indexOf('function parcelPolicyBadges('), source.indexOf('// Return tracking is a state')), ctx);
for (const compact of [false, true]) {
  const badge = ctx.parcelPolicyBadges({stock_return_required: 1}, compact);
  assert(badge.includes('class="tag stock parcel-policy-tag"'));
  assert(badge.includes('>Stock</span>'));
  assert(!badge.includes('Retour stock'));
  assert(!badge.includes('tag bad'));
  assert.equal(ctx.parcelPolicyBadges({stock_return_required: 0}, compact), '');
}
const policies = ctx.parcelPolicyBadges({open_allowed: 0, is_exchange: 1, stock_return_required: 1});
assert(policies.includes('tag bad parcel-policy-tag'));
assert(policies.includes('tag blue parcel-policy-tag'));
const css = fs.readFileSync('static/style.css', 'utf8');
assert(/\.tag\.stock\s*\{[^}]*background: #fff0e0;[^}]*color: #c65300;/s.test(css));
console.log('PASS: Stock badge is orange in compact/detail views; other policies unchanged');
