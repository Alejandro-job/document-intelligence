# Recuperación y contexto (RAG)

## Implementación actual

`core/context_rag.py` construye unidades documentales y fragmentos de búsqueda.
El índice incorpora encabezados, identificadores explícitos y roles locales.
El ranking usa BM25 y controles por intención/tipo documental. No usa embeddings,
FAISS, una base vectorial ni un recuperador entrenado.

Las ventanas de búsqueda son de hasta 850 caracteres con solapamiento aproximado
de 100 y ajuste por saltos de línea. La respuesta recuperada expande la unidad
estructural y sus antecedentes: no entrega sólo la palabra detonadora.
Una remisión sólo se expande por regla cuando existe un destino único.

1. Localizar el fragmento útil a la consulta/campo.
2. Recuperar cláusula/inciso, encabezado y antecedentes.
3. Conservar continuaciones entre páginas.
4. Resolver remisión única y adjuntar su origen.
5. Llevar nombres, designación, facultades y restricciones al contexto del motor.
6. Contrastar la salida con sus referencias literales.

Ejemplo de fallo observado: un nombre correcto citado en el bloque equivocado
no pasa a ser evidencia válida. El experimento anterior de representantes se
conservó rechazado y sus referencias se reconciliaron después por código.
La procedencia híbrida no se atribuye a una inferencia neural nueva.

## Cómo medirlo

Preparar consultas por documento/campo y relevancias humanas independientes
(`qrels`). Medir Recall@k y MRR sobre el ranking devuelto, y cobertura de cláusulas
remitidas, continuaciones y restricciones. Un bloque no revisado no es negativo.

Separar empresas/expedientes completos entre desarrollo y prueba. No dividir
páginas de una misma acta entre entrenamiento y test. La calidad del recuperador
no se infiere de una probabilidad de Qwen ni de una coincidencia con reglas.

**Estado:** hay código de recuperación; su calidad independiente no está medida.
Este documento no publica métricas inventadas.
