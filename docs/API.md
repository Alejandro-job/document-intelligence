# API local del prototipo

No se expone por defecto fuera de `127.0.0.1`. No implementa IAM multiusuario.
No usar este servidor HTTP de desarrollo como servicio público.

| Método | Ruta | Uso |
|---|---|---|
| GET | `/api/health` | Capacidades reales del entorno; nunca declara producción validada |
| POST | `/api/jobs?filename=acta.pdf&engine=reglas` | Cuerpo binario PDF, hasta 50 MB; devuelve trabajo |
| GET | `/api/jobs` | Hasta 30 trabajos recientes |
| GET | `/api/jobs/{id}` | Estado y etapa |
| GET | `/api/jobs/{id}/document` | Documento para el frontend con páginas y propuestas |
| GET | `/api/jobs/{id}/extraction.json` | JSON de los ocho datos |
| GET | `/api/jobs/{id}/evidence.json` | Evidencia y control |
| GET | `/api/jobs/{id}/context.json` | Contexto estructural y recuperación |
| GET | `/api/jobs/{id}/pages/{n}.jpg` | Imagen de página renderizada |
| GET | `/api/jobs/{id}/backup.zip` | Respaldo autocontenido, incluido original y revisión |
| GET | `/api/jobs/{id}/review` | Revisión actual y número de versión |
| POST | `/api/jobs/{id}/review` | `{base_revision, draft}`; 409 si hubo otra actualización |

`engine=qwen` requiere las bibliotecas opcionales y puede cargar/descargar el
modelo. La operación es explícita; no hace entrenamiento. Repetir el mismo
PDF con código/OCR/motor iguales reutiliza el trabajo. Los trabajos Qwen se
reutilizan dentro de la misma sesión, evitando afirmar una identidad de pesos
desconocida entre reinicios.

Un error previo no se repite automáticamente; puede reenviarse con `retry=1`.
Estados de trabajo: queued, running, needs_review, error. Error de lectura no
se presenta como extracción vacía exitosa. Los datos originales nunca se
sobrescriben por guardar una revisión: ésta queda en otra tabla y en la auditoría.

El nombre del revisor es declarado por quien utiliza el prototipo; no es una
identidad autenticada. El alcance es valor/cita revisados, sin aprobación
automática de vigencia ni exhaustividad.
