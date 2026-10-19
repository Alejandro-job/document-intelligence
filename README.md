# Document Intelligence

Extracción de ocho campos de actas constitutivas con lectura PDF/OCR,
recuperación de contexto y evidencia verificable. Incluye un visor para revisar
el documento completo y fichas manuales de INE y comprobante de domicilio.

**Estado: piloto para revisión humana.** Los resultados automáticos son
propuestas. INE y comprobante tienen captura manual; su extracción automática
no está implementada. La demo publicada y la existencia de este repositorio no
acreditan precisión productiva.

## Inicio rápido

Python 3.12 es el entorno verificado. Desde esta carpeta:

```bash
python -m pip install -r requirements-lectura.lock.txt
python app/server.py
```

Abre `http://127.0.0.1:8000`. Puedes revisar los tres casos sintéticos incluidos
o seleccionar **Procesar PDF** para ejecutar el motor local.

Las páginas con texto nativo utilizable evitan OCR. Para páginas escaneadas
instala Tesseract con español. En Debian/Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-spa
```

El servidor se abre en tu propio equipo y conserva trabajos y revisiones en
`runtime_data/`. El nombre del revisor es declarado, sin autenticación multiusuario.

## Qué devuelve

[Ejemplo completo de JSON](examples/extraccion_ocho_campos.json).

| Campo | Forma de salida |
|---|---|
| `razon_social` | Texto o null |
| `fecha_constitucion` | Fecha ISO o null |
| `numero_escritura` | Texto o null |
| `notario` | Nombre y número, con valores parciales permitidos, o null |
| `socios` | Lista de nombres |
| `representantes_legales` | Lista de nombres |
| `poderes` | Lista de facultades propuestas |
| `capital_social_actual` | Importe decimal como texto y moneda, o null |

Los ocho datos se exportan separados de evidencia, contexto y estados. Un
importe o nombre literal puede requerir revisión de rol, fecha, alcance o vigencia.
Una lista vacía no acredita que no existan más elementos en el documento.

## Motor y contexto

- **Reglas y OCR:** disponibles sin descargar un LLM.
- **Qwen opcional:** instalar `requirements-qwen.txt`, seleccionar Qwen en la
  interfaz y revisar sus propuestas y rechazos. Qwen es un modelo preentrenado
  de terceros; el proyecto no lo entrenó desde cero ni hizo fine-tuning.
- **Recuperación:** BM25 con unidades documentales, encabezados, roles y
  remisiones. No hay base vectorial ni embeddings en el recuperador actual.
- **BETO experimental:** los ensayos anteriores no forman parte del motor de
  decisión entregado. Sus pesos y datasets externos no se incluyen aquí.

## Ejecutar las pruebas

Requiere Node.js 22 para las pruebas del frontend; la app no requiere npm.

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/*.test.mjs
python scripts/verificar_publicacion.py
```

El workflow de `.github/workflows/tests.yml` ejecuta estas comprobaciones en
cada push o pull request. Su primer resultado remoto todavía está pendiente.
Las pruebas del adaptador Qwen usan un generador simulado: no miden precisión
ni prueban el rendimiento de una GPU.

## Procesar un lote y evaluarlo

```bash
python core/extract_batch.py --entrada material_prueba --salida MI_EJECUCION
python core/evaluate_batch.py --referencias material_prueba/etiquetas_y_reglas_esperadas.json --resultados MI_EJECUCION --salida MI_EJECUCION/METRICAS.json
```

El segundo comando evalúa después de la extracción. Las referencias nunca se
pasan al extractor. El caso escaneado requiere Tesseract español.

## Documentación

| Archivo | Contenido |
|---|---|
| [Arquitectura](docs/ARQUITECTURA.md) | Componentes y modos de ejecución |
| [Guía de uso](docs/GUIA_USUARIO.md) | Actas, documentos complementarios y exportación |
| [Contrato JSON](docs/CONTRATO_JSON.md) | Tipos, estados y trazabilidad |
| [API](docs/API.md) | Rutas y manejo de revisiones |
| [RAG](docs/RAG.md) | Recuperación BM25, expansión y evaluación pendiente |
| [Ficha de modelos](docs/MODELOS.md) | Modelos usados, procedencia y límites |
| [Ficha de datos](docs/DATOS.md) | Tres sintéticos, referencias y particiones |
| [Evaluación](docs/EVALUACION.md) | Métricas archivadas y límites |
| [Entrenamiento](docs/ENTRENAMIENTO.md) | Cómo construir datos revisados antes de entrenar |
| [Decisiones](docs/DECISIONES.md) | Justificación técnica y evolución |
| [Code review](docs/CODE_REVIEW_Y_FUNDAMENTOS.md) | Revisión de implementación |
| [Estado](docs/ESTADO.md) | Completado, pendiente y orden de trabajo |
| [Publicar en GitHub](docs/PUBLICACION_GITHUB.md) | Instrucciones para este repositorio |
| [Hugging Face](docs/PUBLICACION_HUGGINGFACE.md) | Qué está preparado y qué no está publicado |
| [Verificación](docs/VERIFICACION.json) | Entorno y comprobaciones locales |

## Estructura

| Carpeta | Responsabilidad |
|---|---|
| `app/` | API local, trabajos, almacenamiento e integración |
| `core/` | Lectura, reglas, contexto, Qwen y validadores |
| `ui/` | Visor, fichas, guardado local y ejemplos sintéticos |
| `examples/` | Ejemplo de salida JSON |
| `material_prueba/` | Tres PDFs sintéticos y referencia original |
| `resultados/sinteticos/` | Resultados archivados; no son una evaluación ciega |
| `tests/` | Pruebas de API, trazabilidad, errores e interfaz |
| `scripts/` | Verificación de publicación e inicio Colab |
| `.github/workflows/` | Pruebas automáticas |

## Colab y Docker

Para abrir la app desde una copia en `/content/document-intelligence`:

```python
%run -i /content/document-intelligence/scripts/iniciar_colab.py
```

El iniciador comprueba el manifiesto, prepara dependencias de lectura y abre la
app en el proxy oficial de Colab. Si modificas archivos, el manifiesto anterior
queda obsoleto; regénéralo con `python scripts/crear_manifiesto.py` después de
revisar el cambio. El manifiesto comprueba integridad, no confianza en el autor.
No se instala ni se consulta Qwen por abrir el visor. Colab no conserva por sí
solo los trabajos cuando termina la sesión: exporta el respaldo.

```bash
docker compose up --build
```

Docker está preparado, sin ejecución verificada en este entorno. El puerto
publicado por Compose se limita a `127.0.0.1`. El servidor estándar de Python
es un prototipo local y no es el servicio de producción.

## Licencia y atribución

La licencia del código propio está pendiente de elección por su autor. Los
modelos y dependencias conservan sus licencias y atribuciones originales; se
incluye el aviso de JSZip en `ui/vendor/JSZIP-LICENSE.md`. No se redistribuyen
pesos, documentos reales, datos personales ni tokens en este paquete.

Se utilizó asistencia de IA para código, pruebas y documentación. La autoría
del proyecto y su presentación son independientes de cualquier institución.
