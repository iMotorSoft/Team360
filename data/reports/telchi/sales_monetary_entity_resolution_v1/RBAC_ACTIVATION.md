# RBAC activation

La autorización no quedó pendiente: el permiso específico está registrado, delegado y efectivo para devfull@telchiai.com en telchi_dev. No se crearon usuarios ni se otorgó FULL_ACCESS.

Se extendió el CLI existente `modules.telchi.provisioning.live_cli --monetary-activation`, reutilizando las garantías de backup privado, DSN loopback team360, identidad de sistema PostgreSQL 18, source hashes y transacción SERIALIZABLE.

[activation_precheck_first.json](activation_precheck_first.json), [activation_plan.json](activation_plan.json), [activation_apply.json](activation_apply.json) y [activation_idempotent.json](activation_idempotent.json) documentan backup recuperable, catálogo, rol monetario acotado, delegación global y asignación administrativa. La segunda aplicación creó cero filas/asignaciones.

La delegación monetaria usa eventos propios y conserva intacta la anterior de latest/coverage. Los grants anteriores conservan un permiso monetario ya aprobado, sin concederlo como efecto de grant-sales. No se modificaron perfiles globales, esquemas ni entitlements de otros clientes.

[effective_authorization.json](effective_authorization.json) acredita cuatro permisos efectivos (source_quantity, latest_documents, coverage y period_billed_amount), verificación live del piloto, negativos para dos identidades existentes y cero permisos del piloto en otro workspace. El handler real ejecutó la operación con el permiso específico en seis turnos HTTP cotejados.

M08 HTTP es una fixture explícita de ausencia de permiso en el harness, no una retirada real del grant piloto. Se conserva esa distinción; los negativos de identidades existentes sí consultan PostgreSQL real. En todos los rechazos hubo cero ejecución Foundation.
