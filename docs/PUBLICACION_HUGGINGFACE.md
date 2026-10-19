# Hugging Face: modelos base, aplicación y publicación

## Estado comprobable de este trabajo

El proyecto descarga Qwen/BETO desde repositorios de terceros. Eso no publica
la aplicación, los pesos ajustados por el usuario ni un dataset propio.
Desde este trabajo no se ha creado o subido un Space en una cuenta del usuario.
Si existe uno publicado por otra vía, debe revisarse su URL antes de documentarlo
como despliegue actual. No se inventa usuario, enlace o revisión.

| Recurso | Qué almacenaría | Estado aquí |
|---|---|---|
| GitHub | Código de la aplicación, documentación y pruebas | Carpeta lista; primer push pendiente |
| Hugging Face Space | Demo ejecutable con su propio repositorio | No publicado desde este trabajo |
| Repositorio de modelo | Pesos/adaptadores propios y model card | No hay checkpoint propio validado entregado |
| Repositorio de dataset | Datos distribuibles y dataset card | No se ha publicado |

## Demo estática

Un Space estático puede mostrar este frontend con los sintéticos. No ejecutaría
el servicio Python, Tesseract o Qwen. Mostraría revisión/captura y las mismas
limitaciones del modo estático. Su carpeta de publicación debe incluir todos
los assets relativos, no sólo el HTML.

Ejemplo de metadatos para el README de un Space estático futuro, copiando la UI
a la raíz del Space y verificando antes todos los enlaces de descarga:

```yaml
---
title: Document Intelligence
sdk: static
app_file: index.html
---
```

Esta es una configuración de referencia; el paquete no afirma que el Space
esté preparado o probado end to end. No se publican PDFs reales para alimentar
la demo ni se introduce un endpoint oculto de inferencia.

## Procesamiento alojado

Para ejecutar OCR/modelo se necesita cómputo y un backend adecuado. El servidor
HTTP estándar actual es local: no debe presentarse como servicio público listo.
Antes de alojarlo hay que definir autenticación, aislamiento de trabajos,
retención, persistencia, errores, recursos y costos. La capacidad y los requisitos
de plan se consultan en la documentación actual; no se promete GPU o Docker gratis.

Publicar un Space y publicar un modelo son operaciones diferentes. Si se entrena
un localizador con datos revisados, sus pesos y ficha se versionarían aparte y
la app referenciaría su revisión. Las probabilidades del modelo no se llaman
precisión sin evaluación independiente.

Fuentes oficiales:

- https://huggingface.co/docs/hub/spaces-overview
- https://huggingface.co/docs/hub/spaces-sdks-static
- https://huggingface.co/docs/hub/model-cards
