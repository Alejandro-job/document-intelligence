# Cómo entrenar el siguiente componente útil

El catálogo de palabras clave propone candidatos; no crea verdad de referencia.
El siguiente trabajo es completar etiquetas reales de relevancia por campo.

1. Fijar un inventario de documentos/empresas y congelar el grupo de prueba.
2. Usar reglas/BM25 para proponer bloques y revisar también lo no recuperado.
3. Etiquetar campo y rol/evento, cita literal, límites de cláusula y restricciones.
4. Incluir negativos reales: titular frente a notario actuante; fecha de registro
   frente a constitución; capital mínimo frente a capital suscrito; nombramiento
   frente a facultades efectivamente otorgadas.
5. Separar train/validación/test por empresa/expediente y deduplicar.
6. Medir el baseline BM25 + reglas antes de ajustar una red.
7. Entrenar un localizador por campo si las etiquetas lo permiten; compararlo en
   el mismo protocolo, sin transformar automáticamente los pendientes en negativos.
8. Medir recuperación, extracción, citas, abstención y errores críticos por separado.

No asignar relevancia por número par/impar de fila, balancear ejemplos inventados
para completar clases o mezclar fragmentos de la misma acta entre train/test.
La revisión humana es la fuente de etiquetas; los modelos proponen.

Conservar semilla, versiones, modelo base y commit, IDs de partición, conteos
por campo/clase, historial de pérdida, métricas, errores y pesos finales. El
checkpoint elegido se decide con validación; el test se evalúa al final.

No hay un mínimo universal de documentos que garantice producción. Definir la
cobertura de formatos, casos difíciles y errores permitidos con el uso concreto;
seguir incorporando expedientes mientras aparezcan fallos relevantes.
