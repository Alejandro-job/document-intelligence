# Publicar el repositorio

Nombre propuesto: `document-intelligence`, bajo tu cuenta `Alejandro-job`.
El nombre es una propuesta; no es una URL de repositorio ya creado.

## Crear el destino

En [GitHub / Nuevo repositorio](https://github.com/new), selecciona tu cuenta,
nombre y visibilidad. Puedes comenzar privado y decidir después si publicas.
Crea un repositorio vacío: sin README, licencia o gitignore generados por GitHub,
porque esta carpeta ya contiene su propia documentación.

La licencia del código propio sigue pendiente de elección; el paquete no la
asigna por ti. La documentación conserva las atribuciones de dependencias.

## Subir desde tu PC

Descomprime el paquete y abre PowerShell dentro de `document-intelligence`.
Necesitas Git instalado. Sustituye `PEGA_AQUI_LA_URL_COPIADA_DE_GITHUB` por la
URL del repositorio vacío que acabas de crear; no es un token.

```powershell
git init -b main
git add .
python scripts/verificar_publicacion.py
git status --short
git commit -m "Initial document intelligence pilot"
git remote add origin PEGA_AQUI_LA_URL_COPIADA_DE_GITHUB
git push -u origin main
```

Si Git pide nombre/correo de autor, configúralos con tus datos en el repositorio.
La autenticación se hace con el mecanismo de GitHub/Git de tu equipo; no pegues
contraseñas ni tokens en los archivos o en esta conversación.

Si el repositorio ya contiene trabajo, no uses un push forzado: clónalo y crea
una rama para incorporar esta carpeta. Revisa los cambios antes de integrarlos.

## Después del primer push

1. Abre **Actions** y comprueba el workflow **Pruebas del proyecto**.
2. Verifica README, arquitectura, JSON de ejemplo e instalación desde un clon limpio.
3. Añade capturas revisadas sólo con sintéticos; el QA visual sigue pendiente.
4. Cuando esos pasos pasen, crea una primera versión de piloto, por ejemplo `v0.1.0`.
5. Enlaza la demo de Hugging Face únicamente cuando exista y la hayas comprobado.

La comprobación de publicación valida nombres/tipos y los PDFs sintéticos
permitidos; no certifica de forma automática la ausencia de información personal
en cualquier texto nuevo que añadas.

Guía oficial: https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository
