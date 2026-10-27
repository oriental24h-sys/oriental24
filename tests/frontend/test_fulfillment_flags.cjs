const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync('static/logistics.js', 'utf8');
const app = fs.readFileSync('static/app.js', 'utf8');
let html = '', submit, posted;
const ctx = vm.createContext({
  S: {user: {id: 2, role: 'client'}, cities: [{id: 1, name: 'Agadir', delivery: 1}], hubs: []},
  api: async (path, method, data) => {
    if (path === '/products') return [{id: 5, client_id: 2}];
    assert.equal(path, '/fulfillment/orders');
    assert.equal(method, 'POST'); posted = data; return {id: 9};
  },
  financeKey: () => 'a'.repeat(32), modal: (title, body) => {html = body}, form: body => body,
  clientTrackingSlot: () => '', clientOptions: () => [],
  input: name => `<input name="${name}">`, select: name => `<select name="${name}"></select>`,
  textarea: name => `<textarea name="${name}"></textarea>`, icon: () => '',
  $: () => null, bindClientTracking: () => {}, bindForm: fn => {submit = fn},
  document: {querySelectorAll: () => [{querySelector: selector => ({value: selector === 'select' ? '5' : '2'})}]},
  refresh: async () => {}, renderView: async () => {}, toast: (msg, error) => {if (error) throw Error(msg)},
});
vm.runInContext(source.slice(source.indexOf('let fulfillmentProducts='), source.indexOf('const legacyClientInvoicesView=')), ctx);
vm.runInContext('addFulfillmentLine=()=>{};openFulfillment=async()=>{};', ctx);
(async () => {
  for (const role of ['client', 'admin']) {
    ctx.S.user.role = role;
    await ctx.newFulfillment();
    assert(html.includes('Ne pas autoriser à ouvrir le colis'));
    assert(html.includes('Commande avec échange'));
    for (const name of ['not_allowed_to_open', 'is_exchange']) {
      const tag = html.match(new RegExp(`<input[^>]*name="${name}"[^>]*>`))[0];
      assert(tag.includes('type="checkbox"')); assert(!tag.includes('checked'));
    }
    for (const noOpen of [false, true]) for (const exchange of [false, true]) {
      await submit({not_allowed_to_open: noOpen, is_exchange: exchange});
      assert.strictEqual(posted.not_allowed_to_open, noOpen);
      assert.strictEqual(posted.is_exchange, exchange);
      assert.equal(posted.items[0].product_id, 5); assert.equal(posted.items[0].quantity, 2);
    }
  }
  assert(source.includes('${parcelPolicyBadges(o.shipping)}'));
  const badges = vm.createContext({});
  vm.runInContext(app.slice(app.indexOf('function parcelPolicyBadges('), app.indexOf('// Return tracking is a state')), badges);
  assert.equal(badges.parcelPolicyBadges({}), '');
  assert.equal(badges.parcelPolicyBadges({open_allowed: 1, is_exchange: 0}), '');
  const enabled = badges.parcelPolicyBadges({open_allowed: 0, is_exchange: 1});
  assert(enabled.includes('Non autorisé à ouvrir')); assert(enabled.includes('Échange prévu'));
  console.log('PASS: stock form flags for client/admin, unchecked defaults, all payload combinations and reservation badges');
})().catch(error => {console.error(error); process.exitCode = 1});
