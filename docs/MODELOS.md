# Ficha de los componentes de IA

Este proyecto es una aplicación con adaptadores. No entrega un modelo fundacional
propio ni un extractor neuronal entrenado desde cero.

| Componente | Origen | Uso en esta entrega | Evidencia y límites |
|---|---|---|---|
| Qwen2.5-1.5B-Instruct | Qwen, modelo público | Interpretación opcional del contexto | Sin fine-tuning propio; puede abstenerse o citar mal |
| BETO | dccuchile, modelo público | Experimentos anteriores, fuera del motor entregado | Ensayos pequeños y etiquetas parcialmente arbitrarias; no validados |
| Reglas | Código del proyecto | Extracción y controles deterministas | Evaluación archivada en tres sintéticos conocidos |
| BM25 | Recuperación léxica | Selección de unidades y expansión | No es una red neuronal; métricas independientes pendientes |

## Qwen

- Repositorio base: https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct
- Idioma de los documentos del proyecto: español.
- Adaptación: instrucciones y contexto recuperado; no entrenamiento de pesos.
- Ejecución: local/Colab; CPU o GPU según entorno.
- Salidas: propuestas conservadas junto con respuesta cruda, rechazos y referencias.
- Revisión del modelo: el pipeline actual no fija siempre un commit inmutable;
  si no está registrado, se declara desconocido y no se inventa reproducibilidad.
- Evidencia previa: pilotos de desarrollo. La integración completa de ocho campos
  de este servicio no tiene una evaluación ciega ni una medición GPU end to end.

## BETO y entrenamiento anterior

Base: https://huggingface.co/dccuchile/bert-base-spanish-wwm-uncased

Los ensayos del usuario incluyen clasificación de tipos documentales con pocos
ejemplos y otro entrenamiento de relevancia. En este último se asignaron
etiquetas a filas externas por alternancia, sin soporte documental. Aumentar
épocas o ponderar clases no corrige esas etiquetas. Ese checkpoint no se presenta
como localizador validado ni se utiliza para aprobar evidencia.

No se incluyen sus pesos en este repositorio. No se conocen aquí un commit de
checkpoint final auditado, un test independiente ni métricas de generalización.
No es correcto subir los pesos de Qwen sin modificar como si fueran un modelo propio.

## Publicación de un modelo futuro

Cuando exista un localizador entrenado con etiquetas revisadas, documentar:
modelo base y revisión, dataset y licencia, grupos de partición, semilla,
hiperparámetros, versiones, pérdidas, métricas por campo, errores, recursos,
uso previsto y límites. Sólo entonces acompañar sus pesos/adaptadores de una
model card específica. Una inspección de activaciones/gradientes no sustituye esa evaluación.

Fuentes: repositorios base anteriores y [guía oficial de model cards](https://huggingface.co/docs/hub/model-cards).
