# Ficha de datos

## Material distribuido

Tres PDFs sintéticos, cuatro páginas en total:

| Caso | Tipo | Propósito | Partición |
|---|---|---|---|
| A | Nativo, una página | Constitución simple | Desarrollo conocido |
| B | Escaneado, una página | OCR irregular y datos parciales | Desarrollo conocido |
| C | Dos páginas | Constitución y modificación posterior | Desarrollo conocido |

A y C corresponden a una misma sociedad ficticia. No son tres empresas
independientes ni una prueba de generalización. La referencia original está en
`material_prueba/etiquetas_y_reglas_esperadas.json` y conserva hashes de PDF.
El archivo de referencias conserva siete escenarios. `DISTRIBUCION.json` identifica
los tres PDFs presentes (A/B/C) y los cuatro escenarios cuyo PDF no se distribuye
en esta edición (D/E/F/G). No se contabilizan los ausentes como evaluados.
Los resultados en `resultados/sinteticos/` son archivados del desarrollo anterior.

Los nombres y valores son material de demostración. Los PDFs fueron generados
para el proyecto; no son instrumentos notariales reales ni documentos oficiales.
La selección de una licencia de distribución por el autor sigue pendiente.

## Excluido de la distribución

Documentos reales, capturas de INE, comprobantes, correcciones privadas, archivos
subidos por usuarios, pesos, cachés, carpetas de Drive y datasets externos descargados.
Los corpus legales externos descritos en conversaciones anteriores no aportan
por sí solos etiquetas válidas de los ocho campos de un acta.

## Nuevas etiquetas para avanzar

Cada anotación debe conservar documento/empresa/expediente, SHA-256, página,
fuente, rango, texto literal, campo, rol/evento, relevancia, revisión y notas.
Clases de relevancia: evidencia directa, contexto relacionado, caso confundible
e información ilegible. Lo no revisado conserva ese estado; no es una quinta
clase semántica ni un negativo implícito.

Las listas necesitan revisión de cobertura de páginas para distinguir una
muestra de una lista completa. Una región bien delimitada sin rol correcto no
es una etiqueta positiva suficiente.

Separar por empresa/expediente, deduplicar antes de repartir y congelar un test
con referencias independientes. No usar la respuesta del mismo modelo como
verdad de prueba sin revisión humana.

## Publicación futura

Un dataset en Hugging Face requeriría licencia/permiso de distribución,
descripción de procedencia, esquema de etiquetas, revisión, particiones,
limitaciones y tratamiento de datos personales. Este paquete no publica ese
recurso ni promete la existencia de un corpus real de actas etiquetadas.
