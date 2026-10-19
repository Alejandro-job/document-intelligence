import {esc} from './core.mjs';
import {KINDS,newDossier,validateDossier,attachFile,setManualField,dossierData,downloadPath,detectMime} from './dossier-core.mjs';
import {getDossier,putDossier} from './dossier-store.mjs';
const $=id=>document.getElementById(id);
let options={},record,kind='ine',side='frente',selected='nombres',zoom=1,mark=false,gesture,contextGeneration=0;
let saving=Promise.resolve(),urls=new Map();
const currentCard=()=>record?.fichas[kind];
const currentSha=()=>currentCard()?.lados[side];
const currentFile=()=>record?.archivos[currentSha()];
const error=e=>options.onToast(e.message??String(e),true);
const fileURL=f=>{if(!urls.has(f.sha256))urls.set(f.sha256,URL.createObjectURL(f.blob));return urls.get(f.sha256);};
function disposeURLs(){for(const url of urls.values())URL.revokeObjectURL(url);urls.clear();}
function save(target=record){
 if(!target)return Promise.resolve();target.revision++;target.actualizado=new Date().toISOString();const snapshot=structuredClone(target);
 $('auxSaveStatus').textContent='Guardando…';$('auxSaveStatus').classList.remove('error');
 saving=saving.catch(()=>{}).then(()=>putDossier(snapshot));
 saving.then(()=>{if(record?.documento_base.id===snapshot.documento_base.id)$('auxSaveStatus').textContent='Guardado en este navegador';},e=>{if(record?.documento_base.id===snapshot.documento_base.id){$('auxSaveStatus').textContent='Sin guardar · exporta respaldo';$('auxSaveStatus').classList.add('error');}error(e);});return saving;
}
export async function setDossierContext(owner){
 const generation=++contextGeneration;record=null;disposeURLs();
 try{await saving.catch(()=>{});const saved=await getDossier(owner.id);if(generation!==contextGeneration)return;record=saved?validateDossier(saved,owner.id):newDossier(owner);render();}
 catch(e){if(generation!==contextGeneration)return;record=newDossier(owner);render();error(e);}
}
export function showDossier(next){if(!KINDS[next])return;kind=next;side=next==='ine'?'frente':'documento';selected=KINDS[next].fields[0][0];zoom=1;mark=false;render();}
export function dossierActive(){return document.getElementById('auxView').classList.contains('active');}
function render(){
 const cfg=KINDS[kind];$('auxTitle').textContent=cfg.title;$('auxFieldsTitle').textContent=cfg.subtitle;$('auxOwner').textContent=record?'Vinculado a '+record.documento_base.nombre:'Abriendo el expediente…';$('auxSides').hidden=kind!=='ine';
 $('auxFields').innerHTML=cfg.fields.map(([key,label])=>`<label class="capture-field ${selected===key?'selected':''} ${key==='domicilio'||key==='descripcion'?'wide':''}" data-capture="${key}"><span>${esc(label)}</span><input id="capture_${key}" data-manual-field="${key}" value="${esc(currentCard()?.datos[key]?.valor??'')}" maxlength="8000" autocomplete="off" placeholder="Sin capturar" ${!record?'disabled':''}></label>`).join('');
 $('auxFields').querySelectorAll('input').forEach(input=>{input.onfocus=()=>selectField(input.dataset.manualField);input.oninput=()=>writeField(input.dataset.manualField,{valor:input.value});});
 $('auxEvidenceField').innerHTML=cfg.fields.map(([key,label])=>`<option value="${key}">${esc(label)}</option>`).join('');$('auxNotes').value=currentCard()?.observaciones??'';$('auxReviewer').value=options.getReviewer?.()??'';
 $('auxSave').disabled=!record;$('auxExport').disabled=!record;$('auxUpload').disabled=!record;$('auxEmptyUpload').disabled=!record;
 renderPreview();renderEvidence();
}
function selectField(key){selected=key;const value=currentCard()?.datos[key];if(value&&value.lado!==side){side=value.lado;zoom=1;mark=false;renderPreview();}document.querySelectorAll('[data-capture]').forEach(x=>x.classList.toggle('selected',x.dataset.capture===key));renderEvidence();renderRegions();}
function writeField(key,patch){
 try{setManualField(record,kind,side,key,patch,options.getReviewer?.()??'');save();if(key===selected)renderRegions();}
 catch(e){error(e);}
}
function renderEvidence(){
 const v=currentCard()?.datos[selected];$('auxEvidenceField').value=selected;$('auxEvidencePage').value=v?.pagina??1;$('auxEvidencePage').disabled=currentFile()?.tipo!=='application/pdf';$('auxEvidenceQuote').value=v?.cita_literal??'';
 $('auxRegionStatus').textContent=v?.region?'Región vinculada a '+(record.archivos[v.archivo_sha256]?.nombre??'archivo')+' · '+v.lado:'Sin región marcada.';
}
function renderPreview(){
 const f=currentFile();$('auxFilename').textContent=f?.nombre??'Añade tu documento';$('auxSides').querySelectorAll('[data-side]').forEach(x=>x.classList.toggle('selected',x.dataset.side===side));
 $('auxEmpty').hidden=!!f;$('auxPreview').replaceChildren();$('auxOpenOriginal').hidden=!f;
 const pdf=f?.tipo==='application/pdf';$('auxFields').querySelectorAll('input').forEach(x=>x.disabled=!f);$('auxEvidenceQuote').disabled=!f;$('auxEvidencePage').disabled=!f||!pdf;$('auxClearRegion').disabled=!f;for(const id of ['auxZoomIn','auxZoomOut','auxFit','auxMark'])$(id).disabled=!f||pdf;
 $('auxMark').classList.toggle('selected',mark&&!pdf);$('auxMark').setAttribute('aria-pressed',String(mark&&!pdf));$('auxViewport').classList.toggle('marking',mark&&!pdf);
 $('auxPreviewHint').textContent=!f?'Hasta 25 MB por archivo.':pdf?'Usa los controles del PDF. Indica página y cita en la ficha.':'Arrastra para mover · selecciona un campo y pulsa Marcar campo para señalarlo.';
 if(!f)return;
 const url=fileURL(f);$('auxOpenOriginal').href=url;
 if(pdf){const frame=document.createElement('iframe');frame.src=url;frame.title=KINDS[kind].title+' · documento original';frame.className='aux-pdf';$('auxPreview').append(frame);}
 else{const paper=document.createElement('div');paper.className='aux-paper';const img=document.createElement('img');img.src=url;img.alt=KINDS[kind].title+' · '+side;img.draggable=false;const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 1000 1000');svg.setAttribute('preserveAspectRatio','none');paper.append(img,svg);$('auxPreview').append(paper);resizeDossier();renderRegions();}
}
export function resizeDossier(){const paper=$('auxPreview')?.querySelector('.aux-paper');if(paper)paper.style.width=Math.round(Math.max(260,Math.min(850,$('auxViewport').clientWidth-40))*zoom)+'px';if($('auxZoomValue'))$('auxZoomValue').textContent=Math.round(zoom*100)+'%';}
function addRect(svg,region,active=false,title=''){
 const [x,y,xx,yy]=region,r=document.createElementNS(svg.namespaceURI,'rect');for(const[k,v]of Object.entries({x:x*1000,y:y*1000,width:(xx-x)*1000,height:(yy-y)*1000,fill:active?'#276857':'#596b86','fill-opacity':active?.19:.06,stroke:active?'#276857':'#8795a7','stroke-width':active?3:1.5}))r.setAttribute(k,v);if(title){const t=document.createElementNS(svg.namespaceURI,'title');t.textContent=title;r.append(t);}svg.append(r);return r;
}
function renderRegions(){const svg=$('auxPreview').querySelector('svg');if(!svg)return;svg.replaceChildren();for(const [key,v]of Object.entries(currentCard()?.datos??{}))if(v.region&&v.archivo_sha256===currentSha()&&v.lado===side)addRect(svg,v.region,key===selected,KINDS[kind].fields.find(f=>f[0]===key)?.[1]);}
async function loadFile(file){
 if(!file||!record)return;if(file.size<=0||file.size>25*1024*1024)throw Error('Selecciona un archivo de hasta 25 MB.');
 const target=record,targetKind=kind,targetSide=side,bytes=new Uint8Array(await file.arrayBuffer()),mime=detectMime(bytes),sha=await hash(bytes);
 if(Object.values(target.archivos).reduce((n,f)=>n+f.bytes,0)+(target.archivos[sha]?0:bytes.length)>100*1024*1024)throw Error('Este expediente supera 100 MB. Exporta un respaldo antes de añadir más archivos.');
 attachFile(target,targetKind,targetSide,{sha256:sha,nombre:file.name,tipo:mime,bytes:bytes.length,blob:new Blob([bytes],{type:mime})});
 if(record!==target){await save(target);return;}
 zoom=1;mark=false;render();await save();options.onToast('Archivo guardado. Captura sus datos a la derecha. No se ejecutó OCR.');
}
async function hash(bytes){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');}
export function chooseDossierFile(){$('auxFileInput').click();}
export async function exportDossierJSON(){try{if(!record)throw Error('Espera a que abra el expediente.');await saving.catch(()=>{});options.download(new Blob([JSON.stringify(dossierData(record),null,2)],{type:'application/json'}),'EXPEDIENTE_DOCUMENTAL.json');}catch(e){error(e);}}
export async function exportDossierBackup(){
 try{if(!record)throw Error('Espera a que abra el expediente.');await saving.catch(()=>{});const d=structuredClone(record),z=new JSZip();z.file('EXPEDIENTE_DOCUMENTAL.json',JSON.stringify(dossierData(d),null,2));for(const [sha,f]of Object.entries(d.archivos))z.file(downloadPath(sha,f),await f.blob.arrayBuffer());z.file('LEEME.txt','Respaldo de capturas manuales. Contiene los documentos originales. No se ejecutó extracción automática. Restaura este ZIP desde el mismo expediente base.');options.download(await z.generateAsync({type:'blob',compression:'DEFLATE',compressionOptions:{level:3}}),'EXPEDIENTE_DOCUMENTAL.zip');}
 catch(e){error(e);}
}
async function restore(file){
 if(!file||!record)return;if(file.size>110*1024*1024)throw Error('El respaldo supera 110 MB.');const current=record;let candidate,z;
 if(/\.zip$/i.test(file.name)){z=await JSZip.loadAsync(await file.arrayBuffer());const entries=Object.values(z.files);if(entries.length>500||entries.reduce((n,e)=>n+(e._data?.uncompressedSize??0),0)>110*1024*1024||entries.some(e=>e.unsafeOriginalName?.split('/').includes('..')))throw Error('El respaldo supera el tamaño o contiene rutas no admitidas.');const metadata=z.file('EXPEDIENTE_DOCUMENTAL.json');if(!metadata||metadata._data?.uncompressedSize>5e6)throw Error('No es un respaldo de fichas de documentos.');candidate=JSON.parse(await metadata.async('string'));}
 else{if(file.size>5e6)throw Error('El JSON supera el tamaño previsto.');candidate=JSON.parse(await file.text());}
 validateDossier(candidate,current.documento_base.id);
 for(const [sha,f]of Object.entries(candidate.archivos)){
  const stored=z?.file(downloadPath(sha,f));let blob;
  if(stored){const bytes=await stored.async('uint8array');if(bytes.length!==f.bytes||await hash(bytes)!==sha||detectMime(bytes)!==f.tipo)throw Error('Un archivo no coincide con la ficha del respaldo.');blob=new Blob([bytes],{type:f.tipo});}
  else{blob=current.archivos[sha]?.blob;if(!blob||blob.size!==f.bytes||await hash(new Uint8Array(await blob.arrayBuffer()))!==sha)throw Error('Faltan documentos originales. Restaura el respaldo ZIP que los contiene.');}
  f.blob=blob;
 }
 if(record!==current)throw Error('El expediente cambió mientras se abría el respaldo. Repítelo en el expediente correcto.');
 candidate.historial.push({accion:'restaurar_respaldo',fecha:new Date().toISOString(),fichas_anteriores:structuredClone(current.fichas)});candidate.archivos={...current.archivos,...candidate.archivos};candidate.revision=current.revision;record=candidate;disposeURLs();render();await save();options.onToast('Respaldo restaurado con sus archivos y procedencia manual.');
}
export function initDossier(config){
 options=config;$('auxReviewer').oninput=()=>options.onReviewer?.($('auxReviewer').value);$('auxUpload').onclick=chooseDossierFile;$('auxEmptyUpload').onclick=chooseDossierFile;$('auxFileInput').onchange=()=>loadFile($('auxFileInput').files[0]).catch(error).finally(()=>$('auxFileInput').value='');
 $('auxRestore').onclick=()=>$('auxRestoreInput').click();$('auxRestoreInput').onchange=()=>restore($('auxRestoreInput').files[0]).catch(error).finally(()=>$('auxRestoreInput').value='');$('auxExport').onclick=exportDossierJSON;
 $('auxForm').onsubmit=e=>{e.preventDefault();save().then(()=>options.onToast('Ficha guardada como captura manual pendiente de revisión.')).catch(()=>{});};
 $('auxNotes').oninput=()=>{if(!record)return;currentCard().observaciones=$('auxNotes').value;save();};
 $('auxSides').querySelectorAll('[data-side]').forEach(b=>b.onclick=()=>{side=b.dataset.side;zoom=1;mark=false;renderPreview();});
 $('auxEvidenceField').onchange=()=>selectField($('auxEvidenceField').value);
 $('auxEvidencePage').onchange=()=>{try{const page=Number($('auxEvidencePage').value);if(!Number.isInteger(page)||page<1||page>1000)throw Error('Indica una página entre 1 y 1000.');writeField(selected,{pagina:page});}catch(e){error(e);}};
 $('auxEvidenceQuote').oninput=()=>writeField(selected,{cita_literal:$('auxEvidenceQuote').value});$('auxClearRegion').onclick=()=>{writeField(selected,{region:null});renderEvidence();};
 $('auxZoomIn').onclick=()=>{zoom=Math.min(3,zoom+.2);resizeDossier();};$('auxZoomOut').onclick=()=>{zoom=Math.max(.4,zoom-.2);resizeDossier();};$('auxFit').onclick=()=>{zoom=1;resizeDossier();};$('auxMark').onclick=()=>{mark=!mark;renderPreview();};
 $('auxViewport').addEventListener('pointerdown',e=>{if(e.button!==0||!currentFile()||currentFile().tipo==='application/pdf')return;const viewport=$('auxViewport'),paper=e.target.closest('.aux-paper');if(mark&&!paper)return;
  const box=paper?.getBoundingClientRect();gesture={x:e.clientX,y:e.clientY,left:viewport.scrollLeft,top:viewport.scrollTop,box,mode:mark?'mark':'pan'};if(mark){gesture.start=[Math.max(0,Math.min(1,(e.clientX-box.left)/box.width)),Math.max(0,Math.min(1,(e.clientY-box.top)/box.height))];gesture.rect=addRect(paper.querySelector('svg'),[...gesture.start,...gesture.start],true);}
  viewport.setPointerCapture(e.pointerId);viewport.classList.add('dragging');e.preventDefault();});
 $('auxViewport').addEventListener('pointermove',e=>{if(!gesture)return;const g=gesture;if(g.mode==='pan'){$('auxViewport').scrollLeft=g.left+g.x-e.clientX;$('auxViewport').scrollTop=g.top+g.y-e.clientY;return;}const [x,y]=g.start,xx=Math.max(0,Math.min(1,(e.clientX-g.box.left)/g.box.width)),yy=Math.max(0,Math.min(1,(e.clientY-g.box.top)/g.box.height));g.region=[Math.min(x,xx),Math.min(y,yy),Math.max(x,xx),Math.max(y,yy)];for(const[k,v]of Object.entries({x:g.region[0]*1000,y:g.region[1]*1000,width:(g.region[2]-g.region[0])*1000,height:(g.region[3]-g.region[1])*1000}))g.rect.setAttribute(k,v);});
 $('auxViewport').addEventListener('pointerup',()=>{const g=gesture;gesture=null;$('auxViewport').classList.remove('dragging');if(g?.mode==='mark'){if(g.region&&g.region[2]-g.region[0]>.005&&g.region[3]-g.region[1]>.005){writeField(selected,{region:g.region,pagina:1});renderEvidence();}renderRegions();}});
 $('auxViewport').addEventListener('pointercancel',()=>{gesture=null;$('auxViewport').classList.remove('dragging');renderRegions();});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&dossierActive()){mark=false;renderPreview();}});new ResizeObserver(resizeDossier).observe($('auxViewport'));window.addEventListener('beforeunload',disposeURLs);
}
