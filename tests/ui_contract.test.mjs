import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import {FIELDS,validateDocument,initialDraft,extractionData,auditData,validateValue} from '../ui/core.mjs';
const index=JSON.parse(fs.readFileSync(new URL('../ui/data/index.json',import.meta.url)));
test('Los tres casos sintéticos tienen fuentes y páginas autocontenidas válidas',()=>{
 assert.equal(index.documents.length,3);let pages=0;
 for(const item of index.documents){const d=JSON.parse(fs.readFileSync(new URL('../ui/'+item.url,import.meta.url)));validateDocument(d);pages+=d.pages.length;
  for(const p of d.pages){assert.equal(crypto.createHash('sha256').update(p.text).digest('hex'),p.textSha);assert(fs.existsSync(new URL('../ui/'+p.image,import.meta.url)));}
 }assert.equal(pages,4);
});
test('La exportación mantiene ocho campos y no transforma propuestas en aprobaciones',()=>{
 for(const item of index.documents){const d=JSON.parse(fs.readFileSync(new URL('../ui/'+item.url,import.meta.url))),s=initialDraft(d),a=auditData(d,s);assert.deepEqual(Object.keys(extractionData(d,s)),FIELDS);assert.equal(a.aprobacion_documental,false);assert.deepEqual(s.fieldReviews,{});}
});
test('El contrato no inventa el nombre del notario parcial',()=>{assert.deepEqual(validateValue('notario',{nombre:null,numero:18}),{nombre:null,numero:18});assert.throws(()=>validateValue('notario',{nombre:'x',numero:'18'}));});
test('Los controles de procesamiento, JSON, evidencia y entrega están presentes',()=>{const h=fs.readFileSync(new URL('../ui/index.html',import.meta.url),'utf8'),ids=[...h.matchAll(/id="([^"]+)"/g)].map(m=>m[1]);assert.equal(new Set(ids).size,ids.length);for(const id of ['processBtn','processEngine','exportJsonBtn','exportEvidenceBtn','saveServerBtn','deliveryView','viewport','contextPanel'])assert(ids.includes(id));});
