# Evaluación y criterio para decidir el siguiente paso

La comparación reproducible archivada está en `resultados/sinteticos/` y utiliza
los hashes y referencias originales de `material_prueba/`. El extractor no carga
esas referencias. Los tres documentos se usaron durante desarrollo, por lo que
las métricas sirven para diagnóstico y regresión, sin estimar generalización.

## Lectura de los resultados

- A: PDF nativo, una página, constitución.
- B: PDF escaneado, una página con calidad irregular. La razón social obtenida
  termina en `S.A. DE C.YV.` en vez de `S.A. DE C.V.`. Se conserva el error.
- C: dos páginas de una misma sociedad que A; la modificación cambia escritura,
  representante y capital, conservando la fecha constitutiva original.

Razón social: 2/3 coincidencias exactas. Fecha, escritura, socios,
representantes y capital: 3/3 coincidencias por campo en estas referencias.
El notario solo tiene número evaluable: 3/3; nombre personal, no evaluable.
Poderes: conjuntos exactos 3/3, incluyendo un conjunto vacío, bajo un catálogo
explícito de tres categorías. Esa medida no valida atribución, restricciones o
vigencia jurídica. Consultar los TP, FP, FN, cobertura y detalles originales
en `METRICAS_CORREGIDAS.json`.

Se normalizan NFC, caja y espacios; no se reparan letras OCR ni tildes de nombres.
Importes se comparan como Decimal y moneda; listas como conjuntos. Un 100% sobre
tres ejemplos no debe extrapolarse a documentos reales ni al modelo generativo.

## Resultados reales de desarrollo

TIDA tiene ocho propuestas después de controles y fuentes complementarias.
Qwen propuso presidente y secretario, pero citó incorrectamente el soporte.
El proceso posterior conservó su respuesta rechazada y resolvió referencias por
código: designación y otorgamiento en página 19; facultades y restricciones en
páginas 14-16. El origen híbrido se declara. Ningún valor queda aprobado y no se
midió precisión independiente del documento. Los archivos reales permanecen
en la continuidad privada, fuera del ZIP para entregar.

## Métricas que deben medirse de forma separada

| Componente | Medidas |
|---|---|
| Clasificación de entrada | Matriz por nativo/scan/mixto/protegido/corrupto, fallos y cobertura |
| OCR | CER/WER de regiones transcritas independientemente; omisión de tablas |
| Recuperación | Recall@k, MRR y recuperación de continuaciones/restricciones con qrels |
| Extracción escalar | Exactitud normalizada por campo, cobertura y abstención |
| Listas | Precisión/recall/F1 por elemento y conjunto exacto |
| Evidencia | Citas literales válidas, atribución correcta, cobertura de restricciones |
| Operación | Latencias p50/p95, costo, cola, errores, reintentos y revisiones |

## Errores con impacto distinto

Confundir un fedatario titular con el actuante o atribuir poderes ilimitados a
un representante puede habilitar una decisión indebida. Se considera crítico
y debe abstenerse/escalar, aunque todos los nombres sean literales.
Un salto de línea o diferencia de caja puede ser menor si la identidad y la
evidencia siguen siendo inequívocas. Un cambio de letra en razón social no se
repara silenciosamente: puede cambiar la identidad y requiere revisión.

## Criterio de aceptación propuesto

No se aprueban decisiones por completar ocho valores, generar JSON válido o
mostrar un `confidence=0.97`. El último es un número del modelo cuya utilidad
debe contrastarse contra resultados observados. Se mediría calibración y riesgo
selectivo en un conjunto independiente antes de usar un umbral.

Para un piloto asistido: toda propuesta crítica se revisa con evidencia;
fuentes incompatibles, conflictos, contexto omitido, tabla ambigua o OCR ilegible
mantienen abstención/revisión. Los umbrales finales los acuerda el dueño del
proceso después de medir la tasa y severidad de errores.

Para producción: separar empresas y expedientes completos, detectar duplicados
y plantillas compartidas, preparar referencia antes de ver predicciones y
reservar una prueba final sin ajustes. Incluir notarías y años distintos,
rotación, escaneos deficientes, anexos fiscales, varias modificaciones,
revocaciones y restricciones. No mezclar train/test por páginas o fragmentos.
