import {esc} from './core.mjs';
const $=id=>document.getElementById(id);
let connected=false,pendingFile=null,callbacks={},pollTimer=null,delivery;

async function request(url,options={}){
 const r=await fetch(url,{credentials:'same-origin',...options});
 let data;try{data=await r.json();}catch{throw Error('El servidor no devolvió un resultado JSON.');}
 if(!r.ok)throw Error(data.error??`Error ${r.status}`);return data;
}
export function selectProcessFile(file){pendingFile=file;$('processFilename').textContent=file?`${file.name} · ${(file.size/1048576).toFixed(1)} MB`:'Ningún archivo seleccionado.';}
export function backendConnected(){return connected;}
export async function saveServerReview(doc,draft){
 if(!connected||!doc.serverJob)throw Error('Este documento se guarda en el navegador. Exporta su respaldo.');
 return request(`api/jobs/${doc.serverJob}/review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({base_revision:draft.serverRevision??0,draft})});
}
async function openJob(id){const d=await request(`api/jobs/${id}/document`),review=await request(`api/jobs/${id}/review`);await callbacks.onDocument(d,review);}
async function jobs(){
 if(!connected)return;
 try{const data=await request('api/jobs');$('processingJobs').innerHTML=data.jobs.length?`<table class="data-table"><thead><tr><th>Documento</th><th>Motor</th><th>Estado</th><th>Resultado</th></tr></thead><tbody>${data.jobs.map(j=>`<tr><td>${esc(j.filename)}<br><small>${esc(j.id)}</small></td><td>${esc(j.engine)}</td><td>${esc(j.stage)}${j.error?`<p class="help-text">${esc(j.error)}</p>`:''}</td><td>${j.status==='needs_review'?`<button class="inline-button" data-open-job="${j.id}">Abrir y revisar</button><br><a href="api/jobs/${j.id}/extraction.json" download>JSON de datos</a> · `:''}${['needs_review','error'].includes(j.status)?`<a href="api/jobs/${j.id}/backup.zip" download>Respaldo ZIP</a>`:''}</td></tr>`).join('')}</tbody></table>`:'<p class="help-text">Aún no hay trabajos. Selecciona un PDF para comenzar.</p>';
 $('processingJobs').querySelectorAll('[data-open-job]').forEach(b=>b.onclick=()=>openJob(b.dataset.openJob).catch(e=>callbacks.onToast(e.message,true)));
 }catch(e){callbacks.onToast(e.message,true);}
}
async function poll(id){
 try{const job=await request(`api/jobs/${id}`);$('processProgress').textContent=job.stage;await jobs();
  if(job.status==='needs_review'){$('processBtn').disabled=false;await openJob(id);callbacks.onToast('Documento procesado. Los valores son propuestas para revisar.');return;}
  if(job.status==='error'){$('processBtn').disabled=false;throw Error(job.error);}
  pollTimer=setTimeout(()=>poll(id),1600);
 }catch(e){$('processBtn').disabled=false;$('processProgress').textContent=e.message;callbacks.onToast(e.message,true);}
}
async function process(){
 if(!pendingFile)return callbacks.onToast('Selecciona un PDF.',true);
 if(pendingFile.size>50*1024*1024)return callbacks.onToast('El límite es 50 MB.',true);
 $('processBtn').disabled=true;$('processProgress').textContent='Cargando el PDF al servidor local…';
 try{const job=await request(`api/jobs?filename=${encodeURIComponent(pendingFile.name)}&engine=${encodeURIComponent($('processEngine').value)}`,{method:'POST',headers:{'Content-Type':'application/pdf'},body:pendingFile});clearTimeout(pollTimer);await poll(job.id);}
 catch(e){$('processBtn').disabled=false;$('processProgress').textContent=e.message;callbacks.onToast(e.message,true);}
}
export async function initProcessing(options){
 callbacks=options;$('processFile').onchange=()=>selectProcessFile($('processFile').files[0]);$('processBtn').onclick=process;$('refreshJobs').onclick=jobs;
 $('copyLaunchCode').onclick=()=>callbacks.copyText($('launchCode').textContent);
 $('processEngine').onchange=()=>{$('engineHelp').textContent=$('processEngine').value==='qwen'?'Qwen se ejecuta en este entorno. Puede descargar unos 3 GB si falta el modelo; en CPU puede tardar. Conserva abstenciones y respuestas originales.':'Reglas y contexto documental. No se consulta ni se entrena Qwen; cada propuesta conserva su método.';};
 try{const health=await request('api/health');if(!health.ok)throw Error('Sin motor');connected=true;$('backendStatus').textContent='Motor local conectado';$('backendStatus').className='status-pill green';$('backendInstructions').hidden=true;$('processBtn').disabled=false;$('refreshJobs').disabled=false;$('processEngine').querySelector('[value="qwen"]').disabled=!health.qwen_bibliotecas;await jobs();}
 catch{$('backendStatus').textContent='Revisión de resultados guardados';$('backendInstructions').hidden=false;$('processBtn').disabled=true;}
}
export async function renderDelivery(){
 try{delivery??=await request('data/entrega.json');const d=delivery;
 $('deliveryContent').innerHTML=`<div class="grid-3"><div class="card"><span class="stat-label">Contrato de salida</span><div class="stat-value">8 campos</div><span class="stat-foot">Datos, evidencia y estado separados</span></div><div class="card"><span class="stat-label">Evaluación disponible</span><div class="stat-value">${d.evaluacion.documentos} casos</div><span class="stat-foot">${esc(d.evaluacion.particion)}</span></div><div class="card"><span class="stat-label">Decisiones automáticas aprobadas</span><div class="stat-value">0</div><span class="stat-foot">La revisión humana permanece explícita</span></div></div>
 <div class="grid-2 section-space"><div class="card"><h2>Archivos de entrega</h2><div class="delivery-links">${connected?'<p class="help-text">Estás ejecutando el paquete local. Conserva el ZIP que utilizaste para iniciarlo.</p>':'<a class="button primary" href="entrega/DOCUMENTOS_ENTREGA.zip" download>Descargar paquete completo</a>'}<a class="button secondary" href="entrega/README.md" download>README y ejecución</a><a class="button secondary" href="entrega/ARQUITECTURA.svg" target="_blank" rel="noopener">Arquitectura</a><a class="button secondary" href="entrega/CODE_REVIEW_Y_FUNDAMENTOS.md" download>Code review y fundamentos</a><a class="button secondary" href="entrega/EVALUACION.json" download>Evaluación por campo</a></div><p class="help-text">Incluye tres PDFs sintéticos distintos, referencia original, CLI, interfaz, servicio local, pruebas y resultados.</p></div>
 <div class="card"><h2>Resultados de desarrollo</h2><table class="data-table"><thead><tr><th>Campo</th><th>Medida</th><th>Resultado</th></tr></thead><tbody>${d.evaluacion.resumen.map(r=>`<tr><td>${esc(r.campo)}</td><td>${esc(r.medida)}</td><td>${esc(r.resultado)}</td></tr>`).join('')}</tbody></table><p class="help-text">${esc(d.evaluacion.limite)}</p></div></div><div class="card section-space"><h2>Estado para entregar</h2><p>${esc(d.alcance)}</p><p class="help-text">La muestra de TIDA conserva propuestas y procedencia de reglas, Qwen y reconciliación. La evaluación real independiente, el alcance jurídico y la operación productiva siguen pendientes.</p></div>`;
 }catch(e){$('deliveryContent').textContent=e.message;}
}
