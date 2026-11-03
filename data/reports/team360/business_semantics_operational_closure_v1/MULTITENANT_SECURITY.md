# Seguridad multitenant

PARTIAL en inspección SQL; BLOCKED en acreditación real con dos tenants autenticados. Las organizaciones existentes no son fixtures autorizadas de prueba.

## Frontera efectiva inspeccionada

repository.py filtra catálogo, texto y vector por organization_id, workspace, módulo, estado published y aprobación published. Vector exige versión vigente, alias/revisión/dimensión. Filtros SQL preceden ORDER BY y LIMIT; no se recupera contenido ajeno para filtrarlo en respuesta.

resolver.py valida workspace-organización e identidad antes del catálogo. Sólo IDs presentes en catálogo autorizado pueden cargar evidencia o referencias conversacionales. No cache persistente en este resolver; el memo nuevo sólo deduplica evidencia por id/versión dentro de una llamada.

owned usa organización/workspace/módulo antes de history o mutación administrativa. history y relation_evidence no autorizan por sí mismos: son puertos internos cuyo caller debe validar. No se certifica seguridad de todos los callers sólo leyendo estos métodos.

## RLS y negativos pendientes

El rol efectivo es superusuario/bypassrls y las tablas no tienen RLS. El control depende de la aplicación; no afirmar protección RLS ni cambiar roles en esta tarea.

MT-01 a MT-10 pendientes con identidad tenant B: exacto, alias, vector, ID, historia, auditoría, propuestas, modificaciones, caches y reinicio. Prueba local foreign_or_retired_reference_never_loads_evidence acredita sólo exclusión en resolver con fixture.
