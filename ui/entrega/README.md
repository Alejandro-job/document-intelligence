# Proyecto documental · Extracción con evidencia

Proyecto de extracción documental con evidencia. Incluye interfaz de revisión,
servicio local y CLI. La salida se puede
reutilizar sin volver a procesar el mismo documento con la misma versión.

**Estado:** preparado para una demostración y revisión humana. No está validado
para producción ni para decisiones automáticas. Publicar el frontend
no certifica el extractor ni aloja un servicio de inferencia en la nube.

## Iniciar en tu computadora

Python 3.10 o posterior, con PyMuPDF y Pillow:

```bash
python -m pip install -r requirements.txt
python app/server.py
```

Abre `http://127.0.0.1:8000`. El servicio se enlaza a tu equipo por defecto.
Elige **Procesar PDF**, selecciona un archivo y escoge el motor. La interfaz
también permite explorar los tres ejemplos sintéticos ya procesados.

Para PDFs escaneados se necesita Tesseract con el modelo español:

```bash
apt-get update
apt-get install -y tesseract-ocr tesseract-ocr-spa
```

En Windows puede instalarse Tesseract por separado y usar la CLI con
`--tessdata RUTA`. Si falta español, el lector conserva el diagnóstico y falla
explícitamente; un fallo de OCR no se convierte en ausencia de los ocho campos.

## Colab

La copia de inicio preparada para el proyecto se ejecuta con:

```python
from google.colab import drive
drive.mount('/content/drive')
%run -i /content/document-intelligence/scripts/iniciar_colab.py
```

Lee el ZIP de entrega junto al script, verifica su integridad, prepara el OCR y
abre una vista amplia de la app dentro de Colab mediante el proxy oficial. No
carga un LLM al abrir la interfaz. Si Qwen ya está cargado y ejecutas con `-i`,
el adaptador puede reutilizarlo. Si falta y eliges Qwen, descargará el modelo de
su repositorio oficial; la caché del runtime se conserva mientras exista éste.

Para utilizar este paquete en otro Colab: descomprímelo en `/content/proyecto_documental`,
instala sus dependencias y ejecuta:

```python
%run -i /content/proyecto_documental/scripts/iniciar_colab.py
```

Los trabajos se guardan en SQLite y archivos de `/content/citi_app_runtime`.
El almacenamiento de Colab es temporal: el botón de respaldo exporta original,
lectura, páginas, JSON y revisiones. No se sincroniza silenciosamente con Drive.

## Qué hace la interfaz

1. Abre el documento completo con miniaturas, número de página, zoom y movimiento.
2. Muestra las ocho propuestas y permite ir a sus citas, contexto y continuaciones.
3. Distingue propuesta, valor revisado, no encontrado y no aplicable en el contrato.
4. Permite marcar regiones y revisar explícitamente valor y evidencia.
5. Descarga el JSON de ocho datos o un JSON con evidencia, contexto y procedencia.
6. Añade fichas manuales de INE (frente y reverso), comprobante y otros documentos,
   con vista previa, campos y regiones en imágenes. No realiza su extracción automática.
7. Exporta e importa un respaldo ZIP autocontenido. Los borradores del navegador
   y las revisiones enviadas explícitamente al servidor son almacenamientos separados.

Una revisión de un valor no acredita por sí sola vigencia externa, exhaustividad
de listas, alcance legal de poderes ni aprobación completa del documento.

## Motores y contexto

- **Reglas:** PyMuPDF por página, OCR español cuando corresponde, etiquetas,
  roles de tablas y eventos simples. No usa Qwen ni BETO.
- **Qwen opcional:** `Qwen/Qwen2.5-1.5B-Instruct` local. Instalar primero
  `requirements-qwen.txt`. Usa recuperación léxica, unidades estructurales,
  remisiones y presupuestos del tokenizador real. Conserva prompt, respuesta,
  límites y rechazos. No rellena sus abstenciones con resultados de reglas.
- Una designación personal con remisión única a facultades puede utilizar el
  adaptador de representantes: nombres/cargos de Qwen; referencias resueltas
  por código. La respuesta original citada incorrectamente se conserva.
- El experimento BETO con etiquetas asignadas parcialmente por alternancia de
  filas no se utiliza para decidir evidencia ni aprobar extracciones.

Qwen es un modelo preentrenado. Procesar archivos o inspeccionar pesos no es
entrenarlo. Este paquete no realiza fine-tuning ni estima una probabilidad de acierto.

## CLI y estructura

```bash
python core/extract_batch.py --entrada material_prueba --salida MI_EJECUCION
python core/evaluate_batch.py --referencias material_prueba/etiquetas_y_reglas_esperadas.json --resultados MI_EJECUCION --salida MI_EJECUCION/METRICAS.json
```

La CLI es el recorrido determinista medido, sin modelo generativo. El servicio
local agrega interfaz, trabajos y el adaptador Qwen opcional.

| Carpeta | Contenido |
|---|---|
| `app/` | API local, trabajos, revisiones versionadas, integración del pipeline |
| `core/` | Lectura, contexto, extracción, esquema y validación |
| `ui/` | Frontend sin compilación; ejemplos sintéticos y JSZip con licencia |
| `material_prueba/` | A nativo, B escaneado irregular, C original con modificación y referencia |
| `resultados/sinteticos/` | Salidas y evaluación archivadas del desarrollo anterior |
| `docs/` | Arquitectura, decisiones, evaluación, code review y criterios de evolución |
| `tests/` | Pruebas de API, revisión, errores y contrato de interfaz |

Los módulos de extracción no reciben ni importan el ground truth. El evaluador
se ejecuta después y verifica el hash del PDF correspondiente a cada referencia.

## Contrato y trazabilidad

`EXTRACCION_OCHO_CAMPOS.json` conserva exactamente razón social, fecha de
constitución, escritura, notario, socios, representantes, poderes y capital.
El contrato JSON Schema está en `core/ESQUEMA_SALIDA.json`; el validador Python
controla tipos, fecha, importes y estados. Se admite `notario.nombre = null`
cuando solo se conoce el número, evitando inventar un nombre personal.
Los importes se expresan como decimal en texto.

La evidencia conserva página, fuente, rango, texto literal y SHA-256. Las cajas
se normalizan contra el renderizado visual y se conservan lecturas alternativas
como fuentes distintas. El OCR no corrige letras silenciosamente.

Estados automáticos: `extraido`, `parcial`, `no_encontrado`, `no_aplicable`,
`pendiente_revision`, `error`; todos con `aprobado = false`.
`no_aplicable` exige justificación literal. Lista vacía no demuestra inexistencia.

## Evaluación disponible

Las métricas archivadas corresponden a tres PDFs sintéticos conocidos de
desarrollo; A y C son de la misma sociedad ficticia. No son una prueba ciega.

| Campo | Resultado archivado |
|---|---|
| Razón social | Coincidencia exacta 2/3; error OCR en la forma jurídica de B |
| Fecha y escritura | 3/3 cada uno |
| Notario | Número 3/3; nombre personal no evaluable, sin referencia |
| Socios y representantes | Conjuntos exactos 3/3 por campo |
| Poderes | Conjuntos exactos 3/3, con un caso sin elementos; no mide alcance legal |
| Capital | Valor y moneda exactos 3/3 |

`docs/EVALUACION.md` explica denominadores, errores y límites. La evidencia
literal y la precisión semántica son controles distintos. No se calculan
Recall@k/MRR sin consultas y relevancias independientes etiquetadas.

Esta distribución incluye sólo los sintéticos A/B/C. Las referencias originales
describen siete escenarios; los otros cuatro PDFs no están incluidos ni se
cuentan como evaluados. No se distribuyen expedientes privados ni muestras de pesos.

## Verificación y límites operativos

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/*.test.mjs
```

Node solo se usa para verificar el frontend, no para ejecutarlo. Los registros
exactos y el entorno están en `docs/VERIFICACION.json`.

Se probaron la API con A/C, caché, PDF protegido/corrupto, ausencia de OCR español,
respaldo autocontenido y revisiones con control de versión. La interfaz de la
demo privada tiene pruebas de datos con las fuentes reales; no hubo QA visual
de navegador en este entorno. El nuevo servicio opcional Qwen de ocho campos
no se ejecutó aquí con GPU. El experimento real guardado de representantes
solo demuestra ese caso y conserva los fallos de citación.

El servicio es local, con una cola de un trabajador y tres trabajos pendientes,
límites de archivo/página y reintentos explícitos por API. Un reinicio marca como
interrumpidos los trabajos activos; no afirma recuperarlos sin reprocesar.
Los revisores se identifican por un nombre declarado, no por IAM.
El servidor HTTP de biblioteca estándar es de prototipo: no se debe exponer a
Internet ni tratar como infraestructura productiva.

Docker es una alternativa reproducible preparada, no verificada en este entorno:

```bash
docker compose up --build
```

El puerto queda publicado únicamente en `127.0.0.1` y los trabajos en un volumen.
No incluye los paquetes pesados de Qwen por defecto.

## Para avanzar a producción

1. Congelar versiones y definir referencias humanas independientes por empresa/expediente.
2. Evaluar extracción, citas, recuperación, abstención y errores críticos en PDFs nuevos.
3. Definir umbrales y el alcance de las decisiones autorizadas con el dueño del proceso.
4. Sustituir el servidor del prototipo por un servicio autenticado y una cola duradera;
   agregar cifrado, retención, roles, auditoría de identidad y recuperación operativa.
5. Validar carga, costos, fallos, privacidad y monitorización antes de aprobar el despliegue.

Las fichas de INE, comprobante y otros documentos permiten captura manual,
procedencia y respaldo. Su extracción automática necesita adaptadores y evaluación propios. El esquema de actas no se aplica como si resolviera esos casos.

## Uso de IA y fuentes técnicas

Se utilizó ChatGPT/Codex para revisar el enunciado, implementar código e interfaz,
preparar pruebas, analizar errores y redactar documentación. Qwen se utilizó en
pilotos reales anteriores de inferencia. Sus salidas no se presentan como ground
truth ni como etiquetas humanas. El entrenamiento de BETO es un experimento separado.

- [Proxy oficial de Colab](https://github.com/googlecolab/colabtools/blob/main/google/colab/output/_util.py).
- [Límites de http.server](https://docs.python.org/3.12/library/http.server.html).
- [PyMuPDF](https://pymupdf.readthedocs.io/) y [Tesseract](https://tesseract-ocr.github.io/).
