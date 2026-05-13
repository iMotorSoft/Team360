# Team360 - Instrucciones Para Agentes

Trabajar siempre desde la raiz del proyecto:

`/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360`

Antes de cambios relevantes, leer:

- `.agents/skills/team360-project/SKILL.md`
- `SrvRestAstroLS_v1/docs/status_actual.md`

Separacion documental:

- Comercial / negocio / producto / reportes no tecnicos: `docs/` y `data/reports/`
- Tecnico / codigo / backend / Astro / migraciones / runtime: `SrvRestAstroLS_v1/docs/`

Estructura documental vigente:

- `docs/README.md`: indice raiz de documentacion no tecnica de runtime.
- `docs/negocio/`: contexto comercial, tesis de negocio, analisis de clientes, mercados y oportunidades.
- `docs/estrategia/`: decisiones de producto/plataforma, continuidad, inventarios y estrategia tecnico-negocio.
- `docs/analisis-tecnico/`: analisis tecnico no operativo, factibilidad y automatizacion que no pertenece al runtime.
- `docs/templates/`: plantillas documentales reutilizables.
- `data/reports/README.md`: indice de reportes y evidencias generadas.
- `data/reports/mercadolibre/netzaj-racing/`: relevamientos publicos, playbook e intents derivados del seller NETZAJ RACING.
- `data/reports/snapshots/`: snapshots historicos de estado del repo o de tareas puntuales.
- `SrvRestAstroLS_v1/docs/`: documentacion tecnica de desarrollo, backend, Astro, runtime, migraciones y estado tecnico.

Regla de ubicacion:

- Un documento narrativo de negocio/producto/estrategia va en `docs/`.
- Una evidencia generada, muestra, reporte exportable o snapshot va en `data/reports/`.
- Una nota tecnica ligada a codigo, backend, Astro, migraciones, runtime o validacion de desarrollo va en `SrvRestAstroLS_v1/docs/`.
- No duplicar el mismo contenido entre `docs/`, `data/reports/` y `SrvRestAstroLS_v1/docs/`; mover o enlazar, segun corresponda.

Convencion para `status_actual.md`:

- `SrvRestAstroLS_v1/docs/status_actual.md`
- Objetivo actual: `desarrollo`

Convencion para status locales por directorio documental:

- Todo directorio documental activo debe tener su propio `status_actual.md`.
- Ese archivo describe el ultimo estado y la ultima accion relevante dentro de ese directorio, no el estado global del proyecto.
- Al crear, mover, eliminar o reorganizar documentos dentro de un directorio, actualizar el `status_actual.md` de ese directorio.
- Si el cambio afecta a una subcarpeta y tambien al indice del padre, actualizar ambos status cuando corresponda.
- `SrvRestAstroLS_v1/docs/status_actual.md` sigue siendo la bitacora tecnica principal de desarrollo.
- Los status locales de `docs/` y `data/reports/` no deben mezclar decisiones tecnicas de runtime con material comercial o reportes.
- Carpetas auxiliares vacias que solo contienen `.gitkeep` no requieren `status_actual.md` hasta tener contenido documental real.

Que significa `desarrollo`:

- bitacora tecnica del estado de implementacion
- decisiones tecnicas y cambios realizados
- validaciones ejecutadas
- pendientes recomendados
- notas operativas o de seguridad relevantes para ingenieria

No interpretar ese documento como material comercial, de ventas, marketing o presentacion ejecutiva.

Si en el futuro se crean estados para otros objetivos, deben declararse de forma explicita.

Ejemplos posibles:

- `comercial`
- `producto`
- `operaciones`

Reglas rapidas:

- No mezclar criterios tecnicos con criterios comerciales.
- No inventar estructuras nuevas fuera del patron actual del repo.
- No tocar `team360_orquestador` salvo que el objetivo lo pida.
- No mezclar browser lab de Mercado Libre con AG-UI o frontend salvo que el objetivo lo pida.
- Preferir cambios chicos, claros y reversibles.
- Actualizar `SrvRestAstroLS_v1/docs/status_actual.md` al cerrar tareas tecnicas importantes.

Formato recomendado para `status_actual.md`:

- `Objetivo: ...`
- `Ultima actualizacion: YYYY-MM-DD`
- `## Estado general`
- `## Acciones realizadas`
- entradas por fecha con titulo corto, por ejemplo: `### 2026-05-13 - Integracion inicial de ...`
- dentro de cada entrada: que se cambio, que no se toco, validacion, riesgos o notas si aplica
- `## Validacion`
- `## Pendientes recomendados`
- `## Notas de seguridad`
- Plantilla base disponible en: `docs/templates/status_actual_template.md`
