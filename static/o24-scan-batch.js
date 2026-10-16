/* Shared A1-style scan collector for flows whose server action is intentionally
   recorded per parcel. Scans stay local until the operator validates; callers
   still invoke the original single-parcel endpoint for each item. */
(function(){
  const soundKind=kind=>{try{window.o24Sound?.signal?.(kind)}catch(e){}};
  const safe=value=>typeof esc==='function'?esc(String(value??'')):String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const normalize=value=>String(value??'').trim().toLocaleUpperCase();

  window.o24ScanCollector=function(root,options={}){
    if(!root)return null;
    const id=String(options.id||'scan').replace(/[^A-Za-z0-9_-]/g,'-');
    const max=Math.max(1,Math.min(500,Number(options.max)||500));
    const inputMax=Math.max(1,Math.min(160,Number(options.inputMax)||160));
    const state={items:[],busy:!!options.initialBusy,destroyed:false,camera:null};
    const message=options.initialMessage||'Scannez un colis avec un lecteur USB, un clavier ou la caméra.';
    root.innerHTML=`<div class="o24-scan-batch">
      <div class="pp-rxbox o24-scan-box" data-o24-scan-box>
        <label for="${id}-input">${safe(options.label||'Scanner les colis')}</label>
        <div class="pp-rx-entry">
          <input id="${id}-input" type="text" maxlength="${inputMax}" autocomplete="off" spellcheck="false" placeholder="${safe(options.placeholder||'Tracking ORIENTAL24 puis Entrée')}">
          <button class="btn primary" type="button" data-o24-add>Ajouter ce colis</button>
          <span class="o24-scan-camera-slot"><button class="btn sm" type="button" data-o24-camera>📷 Caméra du téléphone</button></span>
          <button class="btn sm" type="button" data-o24-sound data-o24-snd aria-pressed="${window.o24Sound?.on?.()!==false}">${window.o24Sound?.on?.()===false?'🔇 Son coupé':'🔊 Son activé'}</button>
          <button class="btn sm" type="button" data-o24-clear>↺ Vider les scans</button>
        </div>
        <div class="pp-rx-cam" data-o24-camera-box hidden><video playsinline muted></video></div>
        <span class="sub pp-rx-camera-state" data-o24-camera-state aria-live="polite">Caméra arrêtée — lecteur USB/Bluetooth ou saisie manuelle disponibles.</span>
        <div class="pp-rx-msg" data-o24-message role="status" aria-live="polite">${safe(message)}</div>
      </div>
      <div class="pp-rx-list o24-scan-list" data-o24-list><p class="sub">Aucun colis scanné pour l’instant.</p></div>
      <div class="pp-validate o24-scan-validate">
        <b data-o24-count>0 colis scanné</b>
        ${options.confirmText?`<label class="pp-consent o24-scan-confirm"><input type="checkbox" data-o24-confirm> <span>${safe(options.confirmText)}</span></label>`:''}
        <button class="btn primary" type="button" data-o24-commit disabled>${safe(options.commitLabel||'Valider les scans')}</button>
        <p class="sub" data-o24-hint>${safe(options.hint||'Les scans restent en attente jusqu’à votre validation.')}</p>
      </div>
    </div>`;

    const input=root.querySelector(`#${id}-input`),addButton=root.querySelector('[data-o24-add]');
    const soundButton=root.querySelector('[data-o24-sound]'),cameraButton=root.querySelector('[data-o24-camera]');
    const cameraBox=root.querySelector('[data-o24-camera-box]'),cameraState=root.querySelector('[data-o24-camera-state]');
    const messageNode=root.querySelector('[data-o24-message]'),list=root.querySelector('[data-o24-list]');
    const countNode=root.querySelector('[data-o24-count]'),hintNode=root.querySelector('[data-o24-hint]');
    const commitButton=root.querySelector('[data-o24-commit]'),confirmNode=root.querySelector('[data-o24-confirm]');
    const itemKey=item=>String((typeof options.key==='function'?options.key(item):(item?.tracking??item?.key))??'').trim();
    const setMessage=(kind,text)=>{if(!messageNode||state.destroyed)return;messageNode.className='pp-rx-msg'+(kind?' '+kind:'');messageNode.textContent=String(text||'')};
    const paint=()=>{
      if(state.destroyed||!root.isConnected)return;
      const n=state.items.length;
      countNode.textContent=typeof options.countLabel==='function'?options.countLabel(n):(n+' colis scanné'+(n===1?'':'s'));
      commitButton.textContent=typeof options.commitLabel==='function'?options.commitLabel(n):(options.commitLabel||'Valider les scans')+(n?' ('+n+' colis)':'');
      commitButton.disabled=state.busy||!n;
      input.disabled=state.busy;addButton.disabled=state.busy;cameraButton.disabled=state.busy;
      soundButton.disabled=state.busy;root.querySelector('[data-o24-clear]').disabled=state.busy;
      if(confirmNode)confirmNode.disabled=state.busy;
      const hint=typeof options.hint==='function'?options.hint(n):options.hint;
      if(hintNode&&hint)hintNode.textContent=hint;
      list.innerHTML=n?state.items.map((item,index)=>{
        const content=typeof options.renderItem==='function'?options.renderItem(item,index):`<b>${safe(item?.tracking||itemKey(item))}</b>`;
        return `<div class="o24-scan-row"><span class="o24-scan-row-content">${content}</span><button type="button" class="pp-rx-x" data-o24-remove="${index}" aria-label="Retirer du lot" title="Retirer du lot" ${state.busy?'disabled':''}>×</button></div>`;
      }).join(''):'<p class="sub">Aucun colis scanné pour l’instant.</p>';
      try{options.onChange?.(state.items.slice(),{busy:state.busy})}catch(e){}
    };
    const ctrl={
      get items(){return state.items.slice()},
      get confirmed(){return !!confirmNode?.checked},
      setMessage,
      remove(itemOrKey){
        const target=typeof itemOrKey==='object'?itemKey(itemOrKey):String(itemOrKey??'').trim();
        const index=state.items.findIndex(item=>item===itemOrKey||itemKey(item)===target);
        if(index<0)return false;
        state.items.splice(index,1);paint();return true;
      },
      clear(){state.items=[];paint()},
      setBusy(value){state.busy=!!value;if(state.busy)try{state.camera?.stop()}catch(e){}paint()},
      destroy(){
        if(state.destroyed)return;
        state.destroyed=true;
        try{state.camera?.stop()}catch(e){}
        state.camera=null;
      },
      focus(){if(!state.destroyed)input?.focus({preventScroll:true})}
    };

    const add=async(raw,fromCamera=false)=>{
      if(state.busy||state.destroyed||!root.isConnected)return;
      const code=String(raw??'').trim();
      if(input)input.value='';
      if(!code){soundKind('err');setMessage('err','Scannez ou saisissez un numéro de suivi.');ctrl.focus();return}
      const normalized=normalize(code);
      if(state.items.some(item=>normalize(itemKey(item))===normalized)){
        if(!fromCamera){soundKind('dup');setMessage('dup','Déjà scanné : '+code);ctrl.focus()}
        return;
      }
      if(state.items.length>=max){soundKind('err');setMessage('err','Limite de '+max+' colis atteinte. Validez le lot avant de continuer.');return}
      state.busy=true;paint();
      try{
        const item=typeof options.resolve==='function'?await options.resolve(code,state.items.slice()):{tracking:code};
        if(!item)throw Error(options.invalidMessage||'Ce tracking ne peut pas être ajouté.');
        const key=normalize(itemKey(item)||code);
        if(state.items.some(existing=>normalize(itemKey(existing))===key)){
          if(!fromCamera){soundKind('dup');setMessage('dup','Déjà scanné : '+(item.tracking||code))}
          return;
        }
        state.items.push(item);soundKind('ok');
        setMessage('ok',typeof options.addedMessage==='function'?options.addedMessage(item,state.items.length):('✓ Ajouté : '+(item.tracking||code)));
      }catch(error){
        soundKind('err');setMessage('err',error?.message||'Vérification impossible.');
      }finally{
        state.busy=false;paint();if(!fromCamera)ctrl.focus();
      }
    };

    const commit=async()=>{
      if(state.busy||state.destroyed||!state.items.length)return;
      if(confirmNode&&!confirmNode.checked){soundKind('err');setMessage('err',options.confirmRequiredMessage||'Confirmez d’abord la réception physique.');confirmNode.focus();return}
      if(typeof options.onCommit!=='function'){soundKind('err');setMessage('err','Validation indisponible.');return}
      state.busy=true;try{state.camera?.stop()}catch(e){}soundKind('done');setMessage('',options.processingMessage||'Validation des scans en cours…');paint();
      try{await options.onCommit(state.items.slice(),ctrl)}
      catch(error){if(!state.destroyed){soundKind('err');setMessage('err',error?.message||'Validation impossible.')}}
      finally{if(!state.destroyed&&root.isConnected){state.busy=false;paint();ctrl.focus()}}
    };

    root.querySelector('[data-o24-clear]').onclick=()=>{
      if(state.busy||!state.items.length)return;
      state.items=[];soundKind('dup');setMessage('dup','Lot vidé — vous pouvez recommencer le scan.');paint();ctrl.focus();
    };
    list.addEventListener('click',event=>{
      const button=event.target.closest('[data-o24-remove]');if(!button||state.busy)return;
      const index=Number(button.getAttribute('data-o24-remove')),item=state.items[index];
      if(item){state.items.splice(index,1);soundKind('dup');setMessage('dup',(item.tracking||itemKey(item))+' retiré du lot.');paint();ctrl.focus()}
    });
    input.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();add(input.value,false)}});
    addButton.onclick=()=>add(input.value,false);
    commitButton.onclick=commit;
    soundButton.onclick=()=>{
      const sound=window.o24Sound;if(!sound?.on||!sound?.set)return;
      sound.set(!sound.on());soundButton.textContent=sound.on()?'🔊 Son activé':'🔇 Son coupé';soundButton.setAttribute('aria-pressed',String(sound.on()));
      if(sound.on())soundKind('ok');
    };
    if(window.o24Cam){
      state.camera=window.o24Cam(cameraBox,cameraButton,cameraState,code=>add(code,true));
      cameraButton.onclick=async()=>{
        if(state.busy)return;
        if(state.camera?.active()){state.camera.stop();return}
        const started=await state.camera?.start();if(started)setMessage('ok','Caméra active : scannez les colis.');
      };
    }else cameraButton.onclick=()=>setMessage('err','Caméra indisponible : utilisez un lecteur USB ou la saisie.');

    for(const item of options.initialItems||[]){
      if(state.items.length>=max)break;
      const key=normalize(itemKey(item));if(key&&!state.items.some(existing=>normalize(itemKey(existing))===key))state.items.push(item);
    }
    paint();
    if(options.focus!==false&&!state.busy)ctrl.focus();
    return ctrl;
  };
})();
