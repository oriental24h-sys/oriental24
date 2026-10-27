const fs = require('fs'), vm = require('vm'), assert = require('assert');
const app = fs.readFileSync('static/app.js', 'utf8');
const logistics = fs.readFileSync('static/logistics.js', 'utf8');
let html = '', title = '', submit, post, configCalls = 0, refreshed = 0;
const order = {id: 5, status: 'Réservé', company: 'Test Client', city: 'Agadir',
  shipping: {recipient: 'Recipient', address: 'Rue test', phone: '0612345678', amount: 200, note: 'Fragile', open_allowed: 0, is_exchange: 1},
  lines: [{sku: 'SKU-A', name: 'Product A', quantity: 2}]};
const state = {user: {role: 'agent', agent_hub_id: 10}, settings: {central_hub_id: '10'}, hubs: [{id: 10, name: 'Hub Central', active: 1}]};
const ctx = vm.createContext({S: state, console,
  esc: String, money: String, date: String, icon: () => '',
  heading: (title, sub, actions) => title+sub+actions,
  simpleTable: (headers, rows) => headers.join('|')+rows.flat().join('|'),
  opsTag: String, parcelPolicyBadges: () => 'POLICY BADGES',
  modal: (t, body) => {title=t;html=body}, form: body => body,
  textarea: name => `<textarea name="${name}"></textarea>`,
  api: async (path, method, data) => {
    if (method === 'POST') {post={path,data};return {ok:true}}
    assert.equal(path, '/fulfillment/orders/5');return order;
  },
  opsConfig: null,
  opsLoadConfig: async () => {configCalls++;ctx.opsConfig={central_hub_id:10,hubs:state.hubs}},
  bindForm: callback => {submit=callback}, refresh: async () => {refreshed++},
  renderView: async () => {}, toast: (message, error) => {if(error)throw Error(message)},
});
vm.runInContext(app.slice(app.indexOf('function canAccessFulfillment('),app.indexOf('function workspacePageTitle(')),ctx);
vm.runInContext(logistics.slice(logistics.indexOf('let fulfillmentProducts='),logistics.indexOf('const legacyClientInvoicesView=')),ctx);
(async () => {
  assert(ctx.canAccessFulfillment());
  assert(ctx.fulfillmentCanPrepare());
  assert(!ctx.fulfillmentCanReserve());
  let page = ctx.fulfillmentView([order]);
  assert(page.includes('Préparer'));assert(!page.includes('newFulfillment()'));
  await ctx.openFulfillment(5);
  assert(html.includes("fulfillmentAction('ship')"));
  assert(!html.includes("fulfillmentAction('cancel')"));
  for (const text of ['SKU-A','Product A','Fragile','Agadir','POLICY BADGES']) assert(html.includes(text),text);
  await ctx.fulfillmentAction('ship');
  assert.equal(title,'Valider la préparation');
  assert(html.includes('Hub Central du stock : Hub Central'));
  assert(html.includes('SKU-A'));assert(html.includes('name="checked" required'));
  assert(!html.includes('<select'));
  await submit({checked:true});
  assert.equal(post.path,'/fulfillment/orders/5/ship');
  assert.strictEqual(post.data.hub_id,10);assert.strictEqual(post.data.checked,true);assert.equal(refreshed,1);
  order.status='Préparé';await ctx.openFulfillment(5);
  assert(!html.includes("fulfillmentAction('ship')"));
  order.status='Réservé';
  state.user.agent_hub_id=20;
  assert(!ctx.canAccessFulfillment());assert(!ctx.fulfillmentCanPrepare());
  await ctx.openFulfillment(5);assert(!html.includes("fulfillmentAction('ship')"));
  state.user.agent_hub_id=10;state.hubs[0].active=0;assert(!ctx.canAccessFulfillment());
  state.hubs[0].active=1;state.settings.central_hub_id=null;assert(!ctx.canAccessFulfillment());
  state.user.agent_hub_id=null;assert(!ctx.canAccessFulfillment());
  state.settings.central_hub_id='10';state.user={role:'admin'};
  await ctx.openFulfillment(5);assert(html.includes("fulfillmentAction('ship')"));assert(html.includes("fulfillmentAction('cancel')"));
  assert(ctx.fulfillmentView([order]).includes('newFulfillment()'));
  state.user={role:'client'};
  await ctx.openFulfillment(5);assert(!html.includes("fulfillmentAction('ship')"));assert(html.includes("fulfillmentAction('cancel')"));
  const before=configCalls;await ctx.fulfillmentAction('cancel');assert.equal(configCalls,before,'Client cancellation must not request admin/Hub configuration');
  await submit({reason:'Client cancelled'});assert.equal(post.path,'/fulfillment/orders/5/cancel');
  // Exercise the real navigation guard, not just the sidebar visibility helper.
  state.user={role:'agent',agent_hub_id:10};
  Object.assign(ctx,{view:'dashboard',listPage:1,adminHubSectionRemoved:()=>false,driverFinanceSectionRemoved:()=>false,clientSectionRemoved:()=>false,
    closeWorkspaceMenu:()=>{},workspacePageTitle:String,document:{querySelectorAll:()=>[]},$:()=>({textContent:''}),window:{scrollTo:()=>{}}});
  vm.runInContext(app.slice(app.indexOf('async function navigate(v)'),app.indexOf('function heading(')),ctx);
  await ctx.navigate('fulfillment');assert.equal(ctx.view,'fulfillment');
  state.user.agent_hub_id=20;await ctx.navigate('fulfillment');assert.equal(ctx.view,'partner-palettes');
  assert(app.includes("(x[0]!=='fulfillment'||canAccessFulfillment(u))"));
  console.log('PASS: Central Hub navigation, permissions, physical checklist, fixed Hub submission, prepared state, Admin/client actions');
})().catch(error=>{console.error(error);process.exitCode=1});
