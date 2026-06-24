# Status actual - docs/templates

Objetivo: `plantillas-documentales`

Ultima actualizacion: 2026-06-24

## Estado general

`docs/templates/` contiene plantillas documentales reutilizables.

## Acciones realizadas

### 2026-06-24 - Default LiteStar para proyectos nuevos

- Se actualizo `project-structure-template.md` para declarar que los proyectos
  nuevos iMotorSoft usan LiteStar/Litestar como servidor Python por defecto.
- Se agrego `ls_iMotorSoft_Srv01.py` como entrypoint backend canonico en la
  estructura base.
- Se dejo explicito que `app.py` no es el archivo principal por defecto y que
  FastAPI solo aplica como excepcion documentada por ADR.
- No se modifico `status_actual_template.md`.

### 2026-06-24 - Plantilla de estructura para proyectos nuevos

- Se agrego `project-structure-template.md` como plantilla reutilizable para
  crear proyectos nuevos con el patron operativo/documental validado en
  Team360.
- La plantilla incluye estructura de directorios, archivos minimos, separacion
  documental, ramas recomendadas, politicas `lat.md`, Playwright, root cause,
  Mermaid, preflight, evidencia PASS/FAIL, secretos, dependencias globales vs
  locales, laboratorio tecnico, deploy, DB runtime y modelos/fallback.
- Se explicito que de gstack `/diagram` se adopta Mermaid como fuente canonica
  versionable, sin instalar gstack ni depender del skill completo.
- No se modifico `status_actual_template.md`.

### 2026-05-13 - Plantilla base de status

- Se mantiene `status_actual_template.md` como plantilla base para bitacoras documentales.
- Se agrego este `status_actual.md` para registrar el ultimo estado del directorio.

## Validacion

- Se corrigio la plantilla reusable sin modificar codigo runtime.
- Se agrego una plantilla nueva sin modificar `status_actual_template.md`.
- Se ejecuto `git diff --check` sin errores de whitespace.

## Pendientes recomendados

- Actualizar este status si se agregan nuevas plantillas o cambia el formato recomendado.
