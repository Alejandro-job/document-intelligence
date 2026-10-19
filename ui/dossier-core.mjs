export const DOSSIER_VERSION='expediente_manual_v1';
export const KINDS={
 ine:{title:'INE',subtitle:'Identidad y domicilio',fields:[['nombres','Nombre(s)'],['apellido_paterno','Apellido paterno'],['apellido_materno','Apellido materno'],['nacionalidad','Nacionalidad (si consta)'],['domicilio','Dirección'],['codigo_postal','Código postal'],['curp','CURP'],['clave_elector','Clave de elector'],['fecha_nacimiento','Fecha de nacimiento'],['vigencia','Vigencia / caducidad']]},
 comprobante:{title:'Comprobante de domicilio',subtitle:'Titular, dirección y fecha',fields:[['titular','Nombre del titular'],['domicilio','Dirección'],['codigo_postal','Código postal'],['fecha_emision','Fecha de emisión'],['tipo_servicio','Tipo de comprobante'],['proveedor','Emisor / proveedor'],['cuenta','Cuenta o referencia']]},
 otro:{title:'Otros documentos',subtitle:'Ficha y observaciones',fields:[['tipo','Tipo de documento'],['titular','Nombre / razón social'],['referencia','Número o referencia'],['fecha','Fecha'],['descripcion','Descripción']]}
};
const clone=v=>structuredClone(v);
const fail=m=>{throw Error(m);};
export const slots=kind=>kind==='ine'?['frente','reverso']:['documento'];
export function newDossier(owner){if(!owner?.id)fail('Selecciona primero el documento base del expediente.');return{schema_version:DOSSIER_VERSION,documento_base:{id:owner.id,nombre:owner.title??owner.filename??owner.id},revision:0,archivos:{},fichas:Object.fromEntries(Object.keys(KINDS).map(k=>[k,{lados:{},datos:{},observaciones:''}])),historial:[],aprobado:false};}
export function validateDossier(d,ownerId){
 if(d?.schema_version!==DOSSIER_VERSION||d.documento_base?.id!==ownerId)fail('El respaldo pertenece a otro expediente. Abre primero su documento base.');
 if(!d.archivos||!d.fichas||Object.keys(d.fichas).sort().join(',')!==Object.keys(KINDS).sort().join(',')||!Number.isInteger(d.revision)||d.revision<0||!Array.isArray(d.historial))fail('El expediente no tiene un formato compatible.');
 for(const [sha,f] of Object.entries(d.archivos))if(!/^[a-f0-9]{64}$/.test(sha)||f.sha256!==sha||!['application/pdf','image/jpeg','image/png','image/webp'].includes(f.tipo)||!Number.isInteger(f.bytes)||f.bytes<=0||f.bytes>25*1024*1024||typeof f.nombre!=='string')fail('Archivo del expediente no válido.');
 for(const [k,c] of Object.entries(d.fichas)){
  if(!KINDS[k]||!c?.datos||!c.lados)fail('Ficha de documento no válida.');
  const allowed=new Set(KINDS[k].fields.map(f=>f[0]));
  for(const [side,sha]of Object.entries(c.lados))if(!slots(k).includes(side)||!d.archivos[sha])fail('El archivo de una cara no está disponible.');
  for(const [field,v]of Object.entries(c.datos)){
   if(!allowed.has(field)||typeof v?.valor!=='string'||v.valor.length>8000||!Number.isInteger(v.pagina)||v.pagina<1||v.pagina>1000||!d.archivos[v.archivo_sha256]||c.lados[v.lado]!==v.archivo_sha256||typeof v.cita_literal!=='string'||v.cita_literal.length>16000)fail('Un dato no coincide con el archivo de su ficha.');
   if(v.region!==null&&(!Array.isArray(v.region)||v.region.length!==4||v.region.some(x=>!Number.isFinite(x)||x<0||x>1)||v.region[2]<=v.region[0]||v.region[3]<=v.region[1]))fail('La región marcada no es válida.');
   if(v.origen!=='captura_manual'||v.estado!=='pendiente_revision'||v.aprobado!==false)fail('La captura manual conserva su estado pendiente de revisión.');
  }
 }
 return d;
}
export function attachFile(d,kind,side,descriptor){
 if(!KINDS[kind]||!slots(kind).includes(side))fail('Tipo de documento no válido.');
 const c=d.fichas[kind],previous=c.lados[side];
 if(previous&&previous!==descriptor.sha256){const retired=Object.fromEntries(Object.entries(c.datos).filter(([,v])=>v.archivo_sha256===previous&&v.lado===side));d.historial.push({accion:'sustituir_archivo',tipo:kind,lado:side,archivo_sha256:previous,datos:clone(retired),fecha:new Date().toISOString()});for(const key of Object.keys(retired))delete c.datos[key];}
 d.archivos[descriptor.sha256]=descriptor;c.lados[side]=descriptor.sha256;validateDossier(d,d.documento_base.id);return d;
}
export function setManualField(d,kind,side,field,patch,reviewer=''){
 const c=d.fichas[kind];if(!c||!KINDS[kind].fields.some(f=>f[0]===field))fail('Campo no válido.');
 const sha=c.lados[side];if(!sha)fail('Carga el archivo antes de capturar sus datos.');
 const old=c.datos[field],same=old?.archivo_sha256===sha&&old?.lado===side;
 c.datos[field]={valor:'',pagina:1,cita_literal:'',region:null,...(same?old:{}),...patch,archivo_sha256:sha,lado:side,origen:'captura_manual',estado:'pendiente_revision',aprobado:false,transcripcion_verificada_por_ocr:false,revisor:reviewer.trim(),actualizado:new Date().toISOString()};
 try{validateDossier(d,d.documento_base.id);}catch(e){if(old)c.datos[field]=old;else delete c.datos[field];throw e;}return c.datos[field];
}
export function dossierData(d){
 validateDossier(d,d.documento_base.id);const out=clone(d);for(const f of Object.values(out.archivos))delete f.blob;
 out.aprobado=false;out.extraccion_automatica=false;out.produccion_validada=false;out.alcance='Captura manual de documentos complementarios. La transcripción y las regiones no se han contrastado por OCR.';return out;
}
export function downloadPath(sha,f){return `ARCHIVOS/${sha}.${({'application/pdf':'pdf','image/jpeg':'jpg','image/png':'png','image/webp':'webp'})[f.tipo]}`;}
export function detectMime(bytes){
 if(bytes.length>=5&&String.fromCharCode(...bytes.slice(0,5))==='%PDF-')return'application/pdf';
 if(bytes[0]===255&&bytes[1]===216&&bytes[2]===255)return'image/jpeg';
 if(bytes.length>=8&&[137,80,78,71,13,10,26,10].every((x,i)=>bytes[i]===x))return'image/png';
 if(bytes.length>=12&&String.fromCharCode(...bytes.slice(0,4))==='RIFF'&&String.fromCharCode(...bytes.slice(8,12))==='WEBP')return'image/webp';
 fail('Selecciona un PDF o una imagen JPG, PNG o WEBP válida.');
}
