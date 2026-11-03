# Effective permissions

AUTH_PASS usa `PermissionConsoleRepository.list_effective_permissions`, no mera existencia en core_permissions. Evidencia completa: [effective_and_security.json](effective_and_security.json).

## Resolución autorizada

Se acredita usuario piloto existente, organización Telchi, workspace telchi_dev, módulo Telchi y los permisos específicos de cada capability.

- Antes: `telchi.sales.source_quantity.read.v1`.
- Después: `telchi.sales.coverage.read.v1`, `telchi.sales.latest_documents.read.v1`, `telchi.sales.source_quantity.read.v1`.
- `BusinessAuthorization.allowed(context, conn, required_permission=...)`: verdadero para ambos grants, con conexión PG real y contexto del workspace correcto.
- Workspace distinto: resolver devuelve `[]` para el mismo piloto.
- Roles de workspace, no globales; sin perfiles nuevos ni grants administrativos al piloto. El administrador Telchi resuelve cero permisos comerciales propios, conservando su rol organization_admin delegado.
- El handler HTTP revalida permisos efectivos dentro del turno; B01 exige latest_documents y B02/B03 coverage. La identidad proviene del resolver telefónico real, no del payload HTTP.
- Pruebas negativas conservan límites tenant/workspace/módulo y permiso específico, sin editar usuarios externos.

## Binding comercial

Los permisos no autorizan SQL libre ni acceso ilimitado: cada rol contiene un único código y cada operación pertenece al registry cerrado acreditado.

- latest: `sales.latest_documents.v1`, OINV activas N/SAP_B1_HANA, DocDate descendente y DocEntry descendente; máximo 50.
- coverage: `sales.coverage.v1`, mismo universo, primera/última fecha y mes con filas, sin completitud certificada.
- Publicación: `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot `1408`; conexión read-only y sin SAP.
