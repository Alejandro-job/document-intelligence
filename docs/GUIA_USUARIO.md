# Guía de uso

## Acta constitutiva

1. Inicia `python app/server.py` y abre la dirección local indicada.
2. Revisa un sintético o usa **Procesar PDF**, selecciona archivo y motor.
3. Espera a que el trabajo termine. Un fallo de lectura aparece como error.
4. Abre el resultado: documento completo a la izquierda; ocho campos a la derecha.
5. Pulsa una página de evidencia o abre **Contexto** para ver la cita y sus continuaciones.
6. Para corregir, escribe tu nombre de revisor, revisa valor/cita y confirma el campo.
7. Descarga el JSON de datos y, por separado, evidencia/contexto o respaldo ZIP.

El respaldo permite continuar en otro navegador. Los cambios guardados sólo en
IndexedDB no se comparten automáticamente con otro dispositivo o con Drive.
La revisión enviada expresamente al servidor usa control de versión; si hay
conflicto, no sobrescribe una revisión más reciente.

## INE y comprobante

Selecciona el expediente base antes de abrir la ficha. Carga PDF/JPG/PNG/WEBP de
hasta 25 MB. INE distingue frente y reverso. Captura los campos visibles, página
y cita transcrita. En imágenes puedes seleccionar un campo y dibujar su región.
El PDF utiliza su visor y la referencia manual de página/cita; no crea cajas OCR.

La ficha exporta JSON con origen manual y SHA-256. El ZIP incluye originales
para poder restaurarla. Si cambias un archivo, sus datos activos anteriores se
retiran y quedan en el historial. No se completan nombres o claves por suposición.

## Límites

El botón de abrir un PDF en la demo estática no ejecuta un servidor oculto.
Para procesar un acta nueva utiliza el servicio local/Colab. Capturar un INE no
lo envía al esquema de actas. No hay verificación oficial de identidad ni de
vigencia externa.
