export const FIELDS=['razon_social','fecha_constitucion','numero_escritura','notario','socios','representantes_legales','poderes','capital_social_actual'];
export const LABELS=['Razón social','Fecha de constitución','Número de escritura','Notario actuante','Socios / accionistas','Representantes legales','Poderes','Capital social actual'];
export const COLORS=['#3674d7','#c18b29','#7d65c9','#27908f','#b2618e','#bb7552','#568c5a','#5b8da9'];
export const HELP={
 razon_social:'Revisa el nombre y la forma jurídica de esta entidad. Una empresa citada puede ser ajena al instrumento.',
 fecha_constitucion:'Distingue constitución, otorgamiento, permiso, firma, inscripción y testimonio. Conserva las fechas y eventos que entren en conflicto.',
 numero_escritura:'Revisa el número de este instrumento, distinguiéndolo de escrituras anteriores citadas.',
 notario:'Identifica al fedatario que interviene, incluyendo al interino o adscrito. El titular del membrete puede estar ausente.',
 socios:'Identifica titulares concretos. Las reglas genéricas, los cargos y las menciones repetidas no acreditan por sí solos la lista completa.',
 representantes_legales:'Busca una designación concreta y su rol. Revisa el alcance y las referencias a otras cláusulas.',
 poderes:'Conserva el destinatario, la cláusula completa y sus restricciones. El título de un poder no acredita su vigencia actual.',
 capital_social_actual:'Distingue montos históricos, aumentos, patrimonio y capital. Una cláusula sin monto no establece un valor actual.'
};
export const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const clone=x=>JSON.parse(JSON.stringify(x));
export const plain=s=>String(s).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('es').replace(/\s+/g,' ').trim();
export const uid=()=>globalThis.crypto?.randomUUID?.()??`web_${Date.now()}_${Math.random().toString(16).slice(2)}`;
export function validRanges(ranges,length){return Array.isArray(ranges)&&ranges.length>0&&ranges.every(r=>Array.isArray(r)&&r.length===2&&Number.isInteger(r[0])&&Number.isInteger(r[1])&&0<=r[0]&&r[0]<r[1]&&r[1]<=length);}
export function evidenceSource(doc,e){const primary=doc.pages?.[e.pagina-1];if(primary?.source===e.fuente_id)return primary;return(doc.additionalSources??[]).find(p=>p.page===e.pagina&&p.source===e.fuente_id);}
export function validateDocument(d){
 if(!d||!/^([a-f0-9]{64})$/.test(d.id)||!Array.isArray(d.pages)||!d.pages.length)throw Error('El documento no tiene lectura e identidad válidas.');
 if(!['train','test','sin_asignar'].includes(d.partition))throw Error('Partición documental inválida.');
 const ids=new Set();
 d.pages.forEach((p,i)=>{if(p.page!==i+1||typeof p.text!=='string'||typeof p.source!=='string'||ids.has(p.source))throw Error('Las páginas están incompletas o sus fuentes están duplicadas.');ids.add(p.source);});
 for(const p of d.additionalSources??[]){if(!Number.isInteger(p.page)||p.page<1||p.page>d.pages.length||typeof p.text!=='string'||ids.has(p.source)||typeof p.textSha!=='string')throw Error('Fuente adicional inválida.');ids.add(p.source);}
 for(const e of d.fragments??[]){const p=d.pages[e.pagina-1];if(e.documento_id!==d.id||e.particion!==d.partition||!p||e.fuente_id!==p.source||!validRanges([e.rango_caracteres],p.text.length)||p.text.slice(...e.rango_caracteres)!==e.texto||e.sha256_texto_fuente!==p.textSha)throw Error('Un fragmento no coincide con su fuente original.');}
 for(const a of [...(d.annotations?.anotaciones??[]),...(d.proposals??[])]){const p=evidenceSource(d,a);if(!p||!validRanges(a.rangos,p.text.length)||a.sha256_texto_fuente!==p.textSha||a.texto_literal!==undefined&&a.rangos.map(([x,y])=>p.text.slice(x,y)).join('\n')!==a.texto_literal)throw Error('Una marca no coincide con su fuente original.');}
 for(const c of FIELDS)validateValue(c,d.values[c]??null);
 return d;
}
export function validateValue(field,v){
 if(!FIELDS.includes(field))throw Error('Campo desconocido.');
 if(v===null)return v;
 if(['razon_social','fecha_constitucion','numero_escritura'].includes(field)&&typeof v!=='string')throw Error('Este campo necesita texto o null.');
 if(field==='fecha_constitucion'&&typeof v==='string'){
  if(!/^\d{4}-\d{2}-\d{2}$/.test(v)||Number.isNaN(Date.parse(v+'T00:00:00Z'))||new Date(v+'T00:00:00Z').toISOString().slice(0,10)!==v)throw Error('La fecha necesita un día válido con formato AAAA-MM-DD.');
 }
 if(['socios','representantes_legales','poderes'].includes(field)&&(!Array.isArray(v)||v.some(x=>typeof x==='string'?!x.trim():!x||typeof x!=='object'||Array.isArray(x)||typeof(x.nombre??x.texto_literal)!=='string')))throw Error('Este campo necesita una lista de textos o elementos documentados compatibles.');
 if(field==='notario'&&(!v||Array.isArray(v)||typeof v!=='object'||Object.keys(v).sort().join(',')!=='nombre,numero'||v.nombre!==null&&(typeof v.nombre!=='string'||!v.nombre.trim())||v.numero!==null&&(!Number.isInteger(v.numero)||v.numero<1)))throw Error('El notario necesita nombre (texto o null) y número (entero positivo o null).');
 if(field==='capital_social_actual'&&(!v||Array.isArray(v)||typeof v!=='object'||!('valor'in v)||typeof v.moneda!=='string'))throw Error('El capital necesita {"valor":"…","moneda":"…"} o null.');
 return v;
}
export function displayValue(v){
 if(v===null||v===undefined)return 'Sin determinar';
 if(Array.isArray(v)){if(!v.length)return 'Sin elementos determinados';return v.map(x=>typeof x==='string'?x:displayValue(x)).join('\n');}
 if(typeof v==='object')return Object.entries(v).filter(([,x])=>x!==null&&x!=='').map(([k,x])=>`${k.replaceAll('_',' ')}: ${typeof x==='object'?displayValue(x):x}`).join(' · ');
 return String(v);
}
export function initialDraft(doc){return {version:'citi_revision_web_v1',documento_id:doc.id,snapshot:doc.snapshot,particion:doc.partition,revision:0,annotations:clone(doc.annotations),fieldReviews:{},labels:{version:'citi_etiquetas_parciales_v1',documento_id:doc.id,particion:doc.partition,revision:0,decisiones:{},historial:[]},history:[]};}
export function validateLabels(doc,state){
 if(state?.version!=='citi_etiquetas_parciales_v1'||state.documento_id!==doc.id||state.particion!==doc.partition||!state.decisiones||typeof state.decisiones!=='object'||!Array.isArray(state.historial))throw Error('Las etiquetas pertenecen a otro documento o partición.');
 const ids=new Set(doc.fragments.map(e=>e.fragmento_id));
 for(const[fid,cs]of Object.entries(state.decisiones)){
  if(!ids.has(fid)||!cs||typeof cs!=='object')throw Error('Etiqueta sin fragmento original.');
  for(const[c,d]of Object.entries(cs))if(!FIELDS.includes(c)||!d||typeof d.valor!=='boolean'||typeof d.revisado_por!=='string'||!d.revisado_por.trim())throw Error('Etiqueta sin decisión humana explícita.');
 }
 return state;
}
export function labelDecision(doc,draft,fid,field,value,reviewer,note=''){
 if(!reviewer?.trim())throw Error('Escribe tu nombre en Revisor antes de guardar.');
 if(!doc.fragments.some(e=>e.fragmento_id===fid)||!FIELDS.includes(field)||![true,false,null].includes(value))throw Error('Fragmento, campo o decisión inválidos.');
 const state=clone(draft.labels);validateLabels(doc,state);
 const before=state.decisiones[fid]?.[field]??null;
 const after=value===null?null:{valor:value,revisado_por:reviewer.trim(),fecha_utc:new Date().toISOString(),nota:String(note).trim()};
 if(after)(state.decisiones[fid]??={})[field]=after;
 else{delete state.decisiones[fid]?.[field];if(Object.keys(state.decisiones[fid]??{}).length===0)delete state.decisiones[fid];}
 state.revision++;state.historial.push({fragmento_id:fid,campo:field,anterior:before,nuevo:after,revisado_por:reviewer.trim(),fecha_utc:new Date().toISOString()});
 return state;
}
export function labelStats(doc,state){return Object.fromEntries(FIELDS.map(c=>{const dd=Object.values(state.decisiones).map(d=>d[c]).filter(Boolean),pos=dd.filter(d=>d.valor).length,neg=dd.length-pos;return[c,{positive:pos,negative:neg,unknown:doc.fragments.length-dd.length,ready:pos>0&&neg>0}];}));}
export function reviewedExamples(doc,state){validateLabels(doc,state);return doc.fragments.filter(e=>Object.keys(state.decisiones[e.fragmento_id]??{}).length).map(e=>{const d=state.decisiones[e.fragmento_id];return {...clone(e),etiquetas:FIELDS.filter(c=>d[c]?.valor===true),campos_revisados:FIELDS.filter(c=>c in d),verificado_humano:true,revisado_por:[...new Set(Object.values(d).map(x=>x.revisado_por))].sort().join('; '),revisiones_por_campo:clone(d)};});}
export function boxesForRanges(page,ranges){if(!validRanges(ranges,page.text.length))return[];return(page.words??[]).filter(w=>ranges.some(([a,b])=>w.a<b&&a<w.b)).map(w=>w.box).filter(b=>Array.isArray(b)&&b.length===4&&b.every(Number.isFinite));}
export function selectRegion(page,box){
 const[x0,y0,x1,y1]=box;
 const words=(page.words??[]).filter(w=>{const[x,y,xx,yy]=w.box;return x0<=(x+xx)/2&&(x+xx)/2<=x1&&y0<=(y+yy)/2&&(y+yy)/2<=y1;}).sort((a,b)=>a.a-b.a);
 if(!words.length)throw Error('La región no incluye palabras de la lectura. Amplíala o revisa el OCR.');
 const ranges=[];for(const w of words){const prev=ranges.at(-1);if(prev&&/^[\s|]*$/.test(page.text.slice(prev[1],w.a)))prev[1]=Math.max(prev[1],w.b);else ranges.push([w.a,w.b]);}
 return{ranges,text:ranges.map(([a,b])=>page.text.slice(a,b)).join('\n')};
}
export function evidenceFor(doc,draft,field){
 const automatic=(doc.proposals??[]).filter(a=>a.campo===field).map(a=>({...a,human:false}));
 const manual=(draft.annotations.anotaciones??[]).filter(a=>a.campo===field&&a.estado!=='eliminado').map(a=>({...a,human:true}));
 return[...manual,...automatic].filter(a=>{const p=evidenceSource(doc,a);return p&&a.sha256_texto_fuente===p.textSha&&validRanges(a.rangos,p.text.length);});
}
export function confirmField(doc,draft,field,value,evidence,reviewer,note=''){
 if(!reviewer?.trim())throw Error('Escribe tu nombre en Revisor antes de confirmar.');validateValue(field,value);
 if(value===null||Array.isArray(value)&&!value.length)throw Error('Sin dato o lista vacía se conserva como abstención. No confirma ausencia en todo el documento.');
 const selected=evidenceFor(doc,draft,field).find(a=>a.id===evidence?.id);
 if(!selected)throw Error('Selecciona una cita del campo antes de confirmar.');
 for(const k of ['pagina','fuente_id','rangos','sha256_texto_fuente','texto_literal'])if(JSON.stringify(selected[k])!==JSON.stringify(evidence[k]))throw Error('La cita de revisión cambió respecto a su fuente seleccionada.');
 return{value:clone(value),evidence:clone(evidence),reviewed_by:reviewer.trim(),reviewed_at:new Date().toISOString(),note:String(note),scope:'valor_y_cita_revisados; vigencia_y_completitud_no_acreditadas'};
}
export function searchPages(doc,query){const q=plain(query);if(q.length<2)return[];return doc.pages.filter(p=>plain(p.text).includes(q)).map(p=>({page:p.page,text:p.text}));}
export function assertDraft(doc,draft){
 if(draft.version!=='citi_revision_web_v1'||draft.documento_id!==doc.id||draft.snapshot!==doc.snapshot||draft.particion!==doc.partition)throw Error('El borrador corresponde a otra versión del documento.');
 validateLabels(doc,draft.labels);
 validateDocument({...doc,annotations:draft.annotations});
 for(const[field,r]of Object.entries(draft.fieldReviews??{})){if(!r?.reviewed_by?.trim())throw Error('Revisión sin revisor.');confirmField(doc,draft,field,r.value,r.evidence,r.reviewed_by,r.note);}
 return draft;
}
export function migrateDraft(doc,previous){
 if(previous.documento_id!==doc.id||previous.particion!==doc.partition)throw Error('El borrador pertenece a otro documento o partición.');
 const migrated=clone(previous);migrated.snapshot=doc.snapshot;
 migrated.migrated_from_snapshot=previous.snapshot;
 assertDraft(doc,migrated);return migrated;
}
export function extractionData(doc,draft){return Object.fromEntries(FIELDS.map(c=>{let v=clone(draft.fieldReviews[c]?.value??doc.values[c]??(['socios','representantes_legales','poderes'].includes(c)?[]:null));if(['socios','representantes_legales','poderes'].includes(c))v=v.map(x=>typeof x==='string'?x:x.nombre??x.texto_literal);return[c,v];}));}
export function auditData(doc,draft){
 assertDraft(doc,draft);
 return{schema_version:'citi_resultado_auditable_v1',documento:{archivo:doc.filename,sha256_pdf:doc.id,snapshot:doc.snapshot},datos:extractionData(doc,draft),
 estados:Object.fromEntries(FIELDS.map(c=>[c,{estado:draft.fieldReviews[c]?'valor_y_cita_revisados':'pendiente_revision',origen:doc.control?.estados?.[c]?.origen??doc.control?.origen??'propuesta_guardada',revision_humana:draft.fieldReviews[c]??null}])),
 evidencias:Object.fromEntries(FIELDS.map(c=>[c,evidenceFor(doc,draft,c)])),contexto_por_campo:doc.contextByField??{},
 control_del_motor:doc.control,propuestas_originales:doc.values,normalizacion_salida:'Listas antiguas con nombre/texto_literal se exportan como textos; el original se conserva.',auditoria_humana:draft.history,produccion_validada:false,aprobacion_documental:false};
}
export function controlledDocument(current,report){
 if(report?.documento?.sha256_pdf!==current.id)throw Error('El JSON pertenece a otro PDF. Abre primero el documento correspondiente.');
 const values=report.datos??(report.campos?Object.fromEntries(FIELDS.map(c=>[c,report.campos[c]?.valor])):null);
 if(!values||Object.keys(values).sort().join(',')!==[...FIELDS].sort().join(','))throw Error('El JSON no contiene los ocho campos del contrato.');
 const d=clone(current);d.values=clone(values);d.serverJob=null;
 for(const s of report.fuentes_adicionales??[]){if(s.sha256_pdf&&s.sha256_pdf!==d.id)throw Error('Fuente adicional de otro documento.');const page=d.pages[s.pagina-1];if(!page)throw Error('Página adicional inexistente.');const converted={page:s.pagina,source:s.fuente_id,text:s.texto,textSha:s.sha256_texto_fuente,words:s.palabras??[],width:page.width,height:page.height};d.additionalSources=(d.additionalSources??[]).filter(x=>x.source!==converted.source);d.additionalSources.push(converted);}
 d.control={...(report.control??{}),estados:clone(report.estados??report.control?.estados??Object.fromEntries(FIELDS.map(c=>[c,report.campos?.[c]?.estado??{estado:'pendiente_revision'}]))),aprobado:false,produccion_validada:false};
 const walk=x=>{if(Array.isArray(x))return x.flatMap(walk);if(!x||typeof x!=='object')return[];if(x.fuente_id&&(x.rango_caracteres||x.rangos)){const ranges=x.rangos??[x.rango_caracteres],p=evidenceSource(d,x);if(!p||!validRanges(ranges,p.text.length)||p.textSha!==x.sha256_texto_fuente)throw Error('La cita del JSON no coincide con una fuente disponible.');const literal=ranges.map(([a,b])=>p.text.slice(a,b)).join('\n');const original=x.texto_literal??x.cita_literal??x.texto;if(original!==undefined&&original!==literal)throw Error('La cita importada no es literal.');return[{...clone(x),rangos:ranges,texto_literal:literal}];}return Object.values(x).flatMap(walk);};
 const proposals=[];d.contextByField={};
 for(const c of FIELDS){const cites=walk(report.evidencias?.[c]??report.campos?.[c]?.evidencia_del_valor??[]),context=walk(report.contexto_por_campo?.[c]??report.campos?.[c]?.contexto_documental??cites);d.contextByField[c]=context;let i=0;for(const e of [...cites,...context]){const a={...e,id:`import_${c}_${i++}`,campo:c,estado:'propuesta',contexto:e.texto_literal.length>180};if(!proposals.some(p=>p.campo===c&&p.fuente_id===a.fuente_id&&JSON.stringify(p.rangos)===JSON.stringify(a.rangos)))proposals.push(a);}}
 d.proposals=proposals;validateDocument(d);return d;
}
