# Estado del proyecto

## Completado en el piloto

- Lectura PDF por página y OCR español mediante adaptador.
- Recuperación BM25 con unidades, encabezados, roles y remisiones.
- Ocho propuestas con tipos, fuentes, rangos, citas y control.
- Reglas y adaptador opcional Qwen con respuestas/rechazos conservados.
- Visor completo, marcas, revisión de campos y exportación JSON/ZIP.
- Fichas manuales vinculadas al expediente: INE, comprobante y otros.
- Tres casos sintéticos distintos con evaluación archivada y límites declarados.
- Pruebas locales y documentación; workflow de GitHub preparado.

## Preparado y todavía sin verificar en su destino

- Primer push a un repositorio propio de este proyecto y ejecución remota de Actions.
- Inicio de esta edición reorganizada en el Colab del usuario.
- Docker: archivos disponibles; construcción y ejecución pendientes.
- Visor: pruebas de datos/contratos disponibles; QA visual real de navegador pendiente.

## Pendiente funcional y de validación

- Dataset humano suficiente e independiente por empresa/expediente.
- Calidad de recuperación medida con consultas y relevancias.
- Evaluación ciega de los ocho campos, citas y errores de contexto.
- Entrenamiento y comparación de un localizador con etiquetas correctas.
- Extracción automática específica de INE y comprobantes.
- Servicio productivo autenticado, almacenamiento/cola durable, carga y recuperación.
- Hugging Face: no se ha publicado desde este trabajo un Space propio ni un modelo derivado.

## Orden de avance

1. Publicar esta base en GitHub y comprobar instalación/pruebas.
2. Revisar visualmente el flujo documento → dato → evidencia → JSON → restauración.
3. Completar referencias humanas y evaluar recuperación y extracción.
4. Corregir fallos medidos y decidir si entrenar el localizador aporta mejora.
5. Preparar demo en Hugging Face con alcance explícito y sintéticos.
6. Decidir el paso a producción con evidencia y operación verificadas.
