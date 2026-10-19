# Decisiones técnicas

El pipeline conserva extracción, interpretación y validación como pasos
distintos. El original es inmutable y su SHA-256, junto con las versiones,
identifica el procesamiento. La API y la CLI producen un contrato reutilizable;
un consumidor no necesita volver a ejecutar OCR ni Qwen.

Se inspecciona cada página. Texto nativo utilizable va a PyMuPDF; las restantes
usan un adaptador Tesseract español. Se conservan texto, layout, cajas, fuentes
alternativas y evidencia. Si no hay lectura accesible o falta OCR, falla la
lectura y se conserva el diagnóstico. Visión multimodal sería una alternativa
para tablas y layouts difíciles después de medir su beneficio/costo.

Reglas identifican etiquetas e identificadores, resuelven fechas/decimales y
comprueban citas. Qwen opcional interpreta fragmentos recuperados con roles y
remisiones; sus abstenciones se conservan. Una cadena estructural única puede
reasignar referencias con procedencia explícita, sin cambiar nombres o cargos.
No se utiliza el BETO experimental como árbitro de evidencia.

Es un workflow determinista con adaptadores de IA. No requiere agentes libres
para este caso. El documento y sus citas son datos no confiables: no se ejecutan
instrucciones del PDF ni se permite que un modelo apruebe el instrumento.

Carga y consulta son síncronas; lectura/OCR/modelo se ejecutan como trabajos en
un único worker del prototipo. SQLite y archivos conservan estado y revisiones;
la concurrencia de revisiones exige una versión esperada. Reintentos son
explícitos. Un reinicio registra interrupción en vez de afirmar éxito.

La interfaz se publica privada para revisión de resultados. El motor Python
se ejecuta localmente o en Colab; no se presenta como servicio cloud desplegado.
En producción se requieren API autenticada, cola durable, almacenamiento de
objetos, cifrado, retención y roles; después, workers separados y escalado según
latencia/costo. Logs operativos no incluyen texto documental en consola.

Toda ambigüedad de identidad, contexto, vigencia, tablas, facultades o revocación
requiere revisión. El esquema y las huellas del código/modelo se guardan. Un
commit de modelo desconocido se declara desconocido, sin inventar fijación.
La autorización productiva depende de referencias independientes y medición
del riesgo, no de la existencia del frontend ni del número de tests aprobados.
