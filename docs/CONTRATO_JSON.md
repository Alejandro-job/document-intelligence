# Contrato JSON y trazabilidad

El archivo `core/ESQUEMA_SALIDA.json` es la referencia formal de los ocho datos.
El ejemplo de `examples/extraccion_ocho_campos.json` procede del sintético A.
Su notario contiene `nombre: null` porque sólo se conoce el número: no se inventa.

- Fecha: texto `AAAA-MM-DD` cuando existe propuesta válida.
- Escritura: texto, evitando perder ceros por conversión numérica.
- Importe: decimal como texto y moneda separada.
- Listas: elementos propuestos; lista vacía no acredita ausencia global.
- `null`: falta de propuesta o información parcial según el estado de control.

`EXTRACCION_OCHO_CAMPOS.json` conserva sólo los datos. El soporte se exporta en
archivos separados: evidencia, contexto, fuente y control. Para consumir los
datos con revisión se necesita leer también esos archivos.

La evidencia incluye documento, página, fuente, SHA-256 del texto, rango de
caracteres y cita literal. Las lecturas alternativas no se mezclan silenciosamente
con la fuente primaria. Cita válida y rol semántico correcto son controles distintos.

Estados: `extraido`, `parcial`, `no_encontrado`, `no_aplicable`,
`pendiente_revision`, `error`. Los resultados automáticos conservan `aprobado=false`.
El validador no afirma vigencia externa ni exhaustividad jurídica.

Las fichas de INE/comprobante tienen otro formato:
`schema_version=expediente_manual_v1`. Su origen es `captura_manual`, su estado
es `pendiente_revision` y la transcripción no se declara verificada por OCR.
No se insertan esos campos en el contrato de actas.
