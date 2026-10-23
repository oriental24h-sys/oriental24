/* Shared display preference. No operational limits or permissions are changed. */
const O24_PAGE_SIZES=[10,20,30,50,80,100,200,500];
const listSizeMemory=new Map();
function listPageSize(){const key=S?.user?.id;if(listSizeMemory.has(key))return listSizeMemory.get(key);try{const n=Number(localStorage.getItem('o24-page-size:'+key));return O24_PAGE_SIZES.includes(n)?n:30}catch(e){return 30}}
function saveListPageSize(n){n=Number(n);if(!O24_PAGE_SIZES.includes(n))return;listSizeMemory.set(S?.user?.id,n);try{localStorage.setItem('o24-page-size:'+S?.user?.id,String(n))}catch(e){}return n}
function listSizeControl(size,action){return `<label class="o24-size-control">Par page <select aria-label="Éléments par page" onchange="${action}">${O24_PAGE_SIZES.map(n=>`<option value="${n}" ${n===size?'selected':''}>${n}</option>`).join('')}</select></label>`}
function changeListPageSize(value,kind){if(!saveListPageSize(value))return;if(kind==='parcels'){listPage=1;drawParcelTable()}else if(kind==='support'){supportOrderPage=1;drawSupportOrders()}else if(kind==='finance'){financePage=1;drawFinanceStatements()}}
function changeServerPageSize(value,kind){if(!saveListPageSize(value))return;const f=kind==='pp'?ppFilters:kind==='rp'?rpFilters:kind==='pc'?pcState:billingFilters;f.size=Number(value);f.page=1;if(kind==='pc')pcSel=new Set();renderView()}
/* Unpaged dashboard tables use the same controls; modal scan/confirmation and print
   tables are deliberately excluded. Existing server pagination is never paged twice. */
(()=>{const states=new WeakMap();let scheduled=false;
 function scan(){scheduled=false;observer.disconnect();
  document.querySelectorAll('#content table').forEach(table=>{
   if(states.has(table)||table.closest('#parcel-table,#support-order-table,.billing-card,.pc-card')||table.closest('[data-no-pagination]'))return;
   const shell=table.closest('.card')||table.parentElement;
   if([...shell.querySelectorAll('.pagination,.billing-pagination')].some(el=>!el.closest('.o24-list-pager')))return;
   const body=table.tBodies[0];if(!body||!table.tHead)return;
   const rows=Array.from(body.rows);if(!rows.length||body.querySelector('input:not([type=checkbox]),select,textarea'))return;
   const anchor=table.closest('.table-wrap')||table;
   const bar=document.createElement('div');bar.className='table-footer o24-list-pager';
   anchor.before(bar);const state={page:1,size:listPageSize()};states.set(table,state);
   function draw(){const pages=Math.max(1,Math.ceil(rows.length/state.size));state.page=Math.max(1,Math.min(state.page,pages));
    body.replaceChildren(...rows.slice((state.page-1)*state.size,state.page*state.size));
    bar.innerHTML=`${listSizeControl(state.size,'')}<span aria-live="polite">${rows.length?(state.page-1)*state.size+1:0}–${Math.min(rows.length,state.page*state.size)} sur ${rows.length}</span><div class="pagination"><button type="button" aria-label="Page précédente" ${state.page===1?'disabled':''}>‹</button><span>${state.page} / ${pages}</span><button type="button" aria-label="Page suivante" ${state.page===pages?'disabled':''}>›</button></div>`;
    bar.querySelector('select').onchange=e=>{state.size=saveListPageSize(e.target.value)||30;state.page=1;draw()};
    const buttons=bar.querySelectorAll('button');buttons[0].onclick=()=>{state.page--;draw()};buttons[1].onclick=()=>{state.page++;draw()};
   }draw();
  });observer.observe(document.body,{childList:true,subtree:true});
 }
 const observer=new MutationObserver(records=>{if(records.every(r=>r.target.closest?.('.o24-list-pager')))return;if(!scheduled){scheduled=true;requestAnimationFrame(scan)}});
 if(document.body){observer.observe(document.body,{childList:true,subtree:true});requestAnimationFrame(scan)}
})();
