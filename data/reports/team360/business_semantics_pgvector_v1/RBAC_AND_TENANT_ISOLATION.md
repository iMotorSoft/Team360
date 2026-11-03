# RBAC e aislamiento

Organización proviene de `core_workspaces.organization_id` y tenant del código persistido en `core_organizations`. Texto del usuario nunca determina tenant, workspace, identidad o permisos.

## Lectura y publicación

La memoria reutiliza identidades/roles Console existentes. El pipeline Telchi verifica acceso comercial antes de recuperar cualquier definición; el resolver revalida usuario activo del workspace y organización.

- Queries de conceptos/FTS/vectores filtran organización, workspace/global-org, módulo/global-org, estado publicado y versión aprobada.
- SQL vectorial además filtra alias, revisión y dimensión compatibles antes del ranking.
- Administración exige miembro activo con rol existente `organization_admin`; no crea roles ni grants nuevos.
- CLI normal recibe Console PASETO por stdin, verifica issuer/key/subject y deriva actor del principal. Propuesta/publicación/retiro/embedding auditan en `core_events`.
- Los aliases publicados son inmutables; nuevos aliases después de aprobar se añaden mediante nueva propuesta/versionado.
- `propose` sobre mismo código crea otra versión; `alias` sólo para propuesta; `publish`, `retire`, `history`, `embed`, `list` completan el procedimiento sin UI.
- Administración `list` incluye propuestas; recuperación runtime sólo incluye publicados.

Ejemplo CLI normal, con trust/credenciales privadas existentes y payload sin secretos:

```bash
printf '%s\n' "$CONSOLE_ACCESS_TOKEN" | uv run python -m modules.business_semantics.cli propose --workspace telchi_dev --module telchi --apply --payload /private/concept-proposal.json
printf '%s\n' "$CONSOLE_ACCESS_TOKEN" | uv run python -m modules.business_semantics.cli publish --workspace telchi_dev --module telchi --apply --payload /private/concept-version.json
printf '%s\n' "$CONSOLE_ACCESS_TOKEN" | uv run python -m modules.business_semantics.cli history --payload /private/concept-id.json
```

Payload propuesta: `code,name,definition,type,context,source,reason,aliases` y links opcionales. Publish/embed: `concept_id,version`. History/retire: `concept_id`. Alias: `concept_id,version,alias`. Una propuesta no se convierte en conocimiento durante chat.

## Garantías ejecutadas y pendientes

SQL real devuelve cero conceptos para otra organización y rechaza scope incompatible. Usuario piloto sin rol administrativo no puede administrar; triggers y tests verifican límites.

Hay recuperación de catálogo con dos usuarios activos Telchi (administrador y piloto), pero **sólo el piloto tiene acceso comercial efectivo**. No se amplió RBAC para completar un test. El segundo usuario HTTP autorizado y un segundo tenant HTTP real quedan bloqueados por fixtures/grants faltantes.

La CLI PASETO normal está implementada, pero no se proporcionó fixture de issuer/token administrativo para ejecutarla de extremo a extremo. Seed/migraciones se hicieron con el bootstrap local DEV explícitamente autorizado, registrando el administrador existente como aprobador; no se presentan como login Console.

Observaciones: hash normalizado, scope y contador; no chat completo, teléfono, nombre o PII adicional. Hash-only necesita una fuente autorizada para revisión de la expresión original; no hay publicación automática.
