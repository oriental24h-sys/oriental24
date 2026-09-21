/* Collapsible navigation and role-filtered notice strips. No third-party scripts. */
menu.push(['COMMUNICATION',[['announcements','bell','Annonces & bandeau',['admin']]]]);titles.announcements='Annonces & bandeau';
let managedAnnouncements=[];
const sidebarMobile=()=>matchMedia('(max-width:720px)').matches;
let sidebarKeyboard=false;
const workspaceBaseShell=shell;
shell=function(){
 workspaceBaseShell();document.body.classList.remove('mobile-nav-open');const side=$('.sidebar');side.id='workspace-sidebar';side.setAttribute('aria-label','Navigation principale');
 side.insertAdjacentHTML('beforeend',`<button class="icon-btn sidebar-close" aria-label="Fermer le menu" onclick="closeWorkspaceMenu(true)">${icon('close')}</button>`);
 side.querySelector('.brand').setAttribute('aria-label','ORIENTAL24 · Accueil');
 side.querySelector('.brand').insertAdjacentHTML('beforeend','<span class="compact-brand" aria-hidden="true">O<span>24</span></span>');
 side.querySelectorAll('[data-nav]').forEach(n=>{const label=n.querySelector('span').textContent;n.setAttribute('aria-label',label);n.title=label});
 $('.mobile-menu').setAttribute('aria-controls','workspace-sidebar');$('.mobile-menu').onclick=toggleWorkspaceMenu;
 side.insertAdjacentHTML('afterend','<button type="button" class="sidebar-backdrop" tabindex="-1" aria-label="Fermer le menu" onclick="closeWorkspaceMenu(true)"></button>');
 $('#root').classList.add('sidebar-auto');$('#root').classList.remove('sidebar-peek');sidebarKeyboard=false;
 side.addEventListener('pointerenter',e=>{if(!sidebarMobile()&&e.pointerType!=='touch')$('#root').classList.add('sidebar-peek')});
 side.addEventListener('pointerleave',()=>{if(!sidebarKeyboard||!side.contains(document.activeElement))$('#root').classList.remove('sidebar-peek')});
 side.addEventListener('focusin',()=>{if(sidebarKeyboard&&!sidebarMobile())$('#root').classList.add('sidebar-peek')});
 side.addEventListener('focusout',()=>{queueMicrotask(()=>{if(!side.contains(document.activeElement)&&!side.matches(':hover'))$('#root').classList.remove('sidebar-peek')})});
 syncWorkspaceMenu();
};
function syncWorkspaceMenu(){
 const side=$('.sidebar'),toggle=$('.mobile-menu');if(!side||!toggle)return;
 const mobile=sidebarMobile(),open=side.classList.contains('open');toggle.setAttribute('aria-expanded',String(mobile&&open));toggle.setAttribute('aria-label',open?'Fermer le menu':'Ouvrir le menu');
 side.inert=mobile&&!open;document.body.classList.toggle('mobile-nav-open',mobile&&open);
}
function closeWorkspaceMenu(focus=false){$('.sidebar')?.classList.remove('open');document.body.classList.remove('mobile-nav-open');syncWorkspaceMenu();if(focus)$('.mobile-menu')?.focus({preventScroll:true})}
function toggleWorkspaceMenu(){if(sidebarMobile()){$('.sidebar').classList.toggle('open');syncWorkspaceMenu();if($('.sidebar').classList.contains('open'))$('.sidebar-close').focus({preventScroll:true})}}
addEventListener('resize',()=>{if(!sidebarMobile())closeWorkspaceMenu();else{$('#root')?.classList.remove('sidebar-peek');syncWorkspaceMenu()}});
document.addEventListener('pointerdown',()=>{sidebarKeyboard=false});
document.addEventListener('keydown',e=>{
 if(e.key==='Tab')sidebarKeyboard=true;
 if(e.key==='Escape'){closeWorkspaceMenu(document.body.classList.contains('mobile-nav-open'));$('#root')?.classList.remove('sidebar-peek')}
 if(e.key==='Tab'&&sidebarMobile()&&$('.sidebar.open')){const nodes=[...$('.sidebar').querySelectorAll('a,button')].filter(n=>n.getClientRects().length&&!n.disabled);const first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}}
});
function announcementMarkup(rows){
 if(!rows.length&&S.settings.announcement)rows=[{id:0,title:'ORIENTAL24',body:S.settings.announcement,kind:'info',link_kind:'none'}];
 if(!rows.length)return '';
 return `<section class="workspace-notices" aria-label="Annonces ORIENTAL24">${rows.map(n=>`<article class="workspace-notice notice-${n.kind}"><span class="notice-symbol" aria-hidden="true">${icon(n.kind==='banner'?'truck':'bell')}</span><div class="notice-copy"><strong dir="auto">${esc(n.title)}</strong><span dir="auto">${esc(n.body)}</span>${n.link_kind==='url'?`<a href="${esc(n.link_url)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">${esc(n.link_label)} ${icon('arrow')}<span class="sr-only"> · site externe, nouvel onglet</span></a>`:n.link_kind==='template'?`<button class="notice-link" onclick="downloadNoticeTemplate()">${esc(n.link_label)} ${icon('download')}</button>`:''}</div>${n.kind==='banner'?`<div class="notice-art" aria-hidden="true">${routeArt()}</div>`:''}</article>`).join('')}</section>`;
}
async function downloadNoticeTemplate(){
 if(opsOffline){offlineUnavailable('Modèle Excel actualisé — version serveur');return}
 if(!['admin','client'].includes(S?.user?.role)){toast('Téléchargement réservé aux espaces Admin et Client.',true);return}
 const owner=S.user.id;try{const r=await fetch('/api/imports/template.xlsx',{credentials:'same-origin'});if(!r.ok)throw Error('Modèle inaccessible. Vérifiez votre connexion et vos droits.');const blob=await r.blob();if(S?.user?.id!==owner)return;const a=document.createElement('a'),url=URL.createObjectURL(blob);a.href=url;a.download='ORIENTAL24-modele-colis.xlsx';a.click();setTimeout(()=>URL.revokeObjectURL(url),1500)}catch(e){if(S?.user?.id===owner)toast(e.message,true)}
}
function announcementsView(rows){
 managedAnnouncements=rows;
 return heading('Annonces & bandeau','Messages affichés au-dessus des pages. Texte, liens et espaces destinataires sont sous votre contrôle.',`<button class="btn" onclick="renderView()">${icon('refresh')}Actualiser</button><button class="btn primary" onclick="announcementForm()">${icon('plus')}Nouvelle annonce</button>`)+`<p class="form-hint notice-manager-hint">Dix annonces actives maximum. L’ordre le plus petit apparaît en premier. Les brouillons ne sont pas envoyés aux autres espaces. L’ancien message de Paramètres → Général sert de repli si aucun message actif ne concerne cet espace. ${opsOffline?'HTML : simulation locale, sans publication sur le serveur.':''}</p><section class="card">${simpleTable(['Annonce','Espaces','Ordre','Publication','Version',''],rows.map(n=>[`<strong>${esc(n.title)}</strong><span class="sub notice-admin-body" dir="auto">${esc(n.body)}</span><span class="sub">${{info:'Information',warning:'Attention',important:'Important',banner:'Grand bandeau'}[n.kind]}${n.link_kind!=='none'?' · avec lien':''}</span>`,n.audience.map(roleName).join(' · '),n.position,`<span class="tag ${n.active?'good':''}">${n.active?'Active':'Inactive / brouillon'}</span>`,n.revision,`<button class="btn sm" onclick="announcementForm(${n.id})">${icon('edit')}Modifier</button>`]))}</section><p class="sub" style="margin-top:14px">Les changements sont relus à la navigation ou à l’actualisation, pas diffusés en temps réel. Le grand bandeau utilise une illustration ORIENTAL24 intégrée ; aucun horaire ou service n’est annoncé automatiquement.</p>`;
}
async function announcementForm(id){
 if(S?.user?.role!=='admin'){toast('Action réservée à Admin.',true);return}
 const owner=S.user.id;modal(id?'Modifier l’annonce':'Nouvelle annonce','<p class="sub">Chargement…</p>',true);const node=$('#modal-root .modal');const current=()=>node.isConnected&&S?.user?.id===owner;
 try{
  let n={title:'',body:'',kind:'info',audience:['admin','client','livreur'],position:10,active:false,link_kind:'none',link_label:'',link_url:''};
  if(id){const rows=await api('/announcements/manage');if(!current())return;n=rows.find(r=>r.id===id);if(!n)throw Error('Annonce introuvable.')}
  node.classList.add('announcement-editor');node.querySelector('.modal-body').innerHTML=form(`${input('title','Titre',n.title,'text',true,'maxlength="120"')} ${select('kind','Présentation',[['info','Information'],['warning','Attention'],['important','Important'],['banner','Grand bandeau']],n.kind)}<div class="full">${textarea('body','Message',n.body,true)}</div><fieldset class="full notice-audience"><legend>Espaces destinataires</legend>${['admin','client','livreur'].map(r=>`<label><input type="checkbox" name="audience" value="${r}" ${n.audience.includes(r)?'checked':''}>${roleName(r)}</label>`).join('')}</fieldset>${input('position','Ordre (0 à 99)',n.position,'number',true,'min="0" max="99" step="1"')}${select('active','Publication',[['false','Inactive / brouillon'],['true','Active · visible aux espaces choisis']],String(n.active))}${select('link_kind','Lien',[['none','Aucun lien'],['url','Site externe HTTPS'],['template','Modèle Excel des villes actuelles']],n.link_kind)}${input('link_label','Texte du lien',n.link_label,'text',false,'maxlength="90"')}<div class="full">${input('link_url','Adresse HTTPS',n.link_url,'url',false,'maxlength="1000" placeholder="https://…"')}</div><div class="full form-hint">Texte simple uniquement. Aucun HTML ni script. Le modèle Excel est réservé à Admin et Client. Un lien externe s’ouvre dans un nouvel onglet ; vérifiez son adresse avant publication.</div><div id="notice-preview" class="full" aria-label="Aperçu de l’annonce"></div>`,'Enregistrer l’annonce');
  const f=node.querySelector('form'),err=f.querySelector('.form-error'),submit=f.querySelector('[type=submit]');f.querySelector('textarea').maxLength=900;let busy=false;
  const values=()=>({title:f.elements.title.value.trim(),body:f.elements.body.value.trim(),kind:f.elements.kind.value,audience:[...f.querySelectorAll('[name=audience]:checked')].map(x=>x.value),active:f.elements.active.value==='true',position:Number(f.elements.position.value),link_kind:f.elements.link_kind.value,link_label:f.elements.link_label.value.trim(),link_url:f.elements.link_url.value.trim()});
  const preview=()=>{const d=values();f.elements.link_label.disabled=d.link_kind==='none';f.elements.link_label.required=d.link_kind!=='none';f.elements.link_url.disabled=d.link_kind!=='url';f.elements.link_url.required=d.link_kind==='url';const safe={...d,title:d.title||'Titre de l’annonce',body:d.body||'Votre message',link_kind:'none'};$('#notice-preview').innerHTML='<span class="sub">Aperçu visuel · pas encore publié</span>'+announcementMarkup([safe])};f.oninput=preview;f.onchange=preview;preview();
  f.onsubmit=async e=>{e.preventDefault();if(busy||!current())return;const d=values();if(!d.audience.length){err.textContent='Choisissez au moins un espace.';err.style.display='block';return}if(id)d.revision=n.revision;busy=true;submit.disabled=true;err.style.display='none';let committed=false;
   try{if(id)await api409(f=>api('/announcements/'+id,'PATCH',{...d,...(f?{revision:f.revision}:{})}),async()=>({revision:(await api('/announcements/manage')).find(x=>x.id===id)?.revision}));else await api('/announcements/manage','POST',d);committed=true;if(!current())return;closeModal();await renderView();if(S?.user?.id===owner)toast('Annonce enregistrée')}
   catch(e){if(current()){err.textContent=e.message;err.style.display='block';err.scrollIntoView({block:'nearest'})}else if(committed&&S?.user?.id===owner)toast('Annonce enregistrée. Actualisez la liste.',true)}finally{busy=false;submit.disabled=false}
  };
 }catch(e){if(current())node.querySelector('.modal-body').innerHTML=`<p class="form-hint" role="alert">${esc(e.message)}</p><button class="btn" onclick="closeModal()">Fermer</button>`}
}

// Leaving the application shell must release the touch-menu scroll lock too.
const workspacePublic=renderPublic,workspaceLogin=renderLogin;
renderPublic=function(...args){closeWorkspaceMenu();return workspacePublic(...args)};
renderLogin=function(...args){closeWorkspaceMenu();return workspaceLogin(...args)};
