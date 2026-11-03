# RBAC activation

Foundation `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot **1408**, CURRENT efectivo confirmado; solo DEV y lectura. Sin SAP, modificaciones canónicas, reingestión, deploy ni cambio de modelo.

Activación realizada con el CLI administrativo existente `modules.telchi.provisioning.live_cli --product-activation`, backup recuperable owner-only en PRIVATE_ROOT, hashes revisados, destino local PostgreSQL 18/team360 y transacción SERIALIZABLE.

Permisos específicos: telchi.products.search.read.v1 y telchi.sales.by_products.read.v1; roles estrechos asignados a devfull@telchiai.com en telchi_dev. Se validan entitlement/delegación comercial previos y se auditan autorización global, delegación Telchi y grant del incremento. Console resuelve ambos permisos efectivos; no FULL_ACCESS ni cambios a otros tenants.

[Aplicación](activation_apply.json), [idempotencia sin cambios](activation_idempotent.json), [Console efectivo](effective_authorization.json). Se preservaron las cuatro capacidades previas. Identidad administrativa Telchi existente sin estos permisos: resultado Console negativo real; no se la impersonó.

La denegación HTTP P13 usa fixture explícita de permiso faltante sobre el handler real; no certifica autenticación de una segunda identidad externa. No se retiraron permisos al piloto ni se usaron allowlists telefónicas para autorizar negocio.
