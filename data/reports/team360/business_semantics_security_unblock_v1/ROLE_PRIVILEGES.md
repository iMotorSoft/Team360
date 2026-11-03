# Privilegios PostgreSQL

El destino local se identifica, pero la conexión candidata runtime no ofrece una segunda barrera PostgreSQL. Gate RUNTIME_DB_PRIVILEGES=BLOCKED; no se alteraron roles, GRANTs ni RLS.

## Resultados efectivos

Las consultas reales están en database_probe.json; se distinguen grants explícitos de capacidades implícitas del superusuario.

Rol/session_user: administrator. rolsuper=true, rolbypassrls=true, rolcreaterole=true, rolcreatedb=true, rolinherit=true. Propietario de team360 y de las ocho tablas business_concept*. SELECT/INSERT/UPDATE/DELETE efectivos: true en todas.

row_security=on **no elimina el bypass de superusuario**. relrowsecurity=false y relforcerowsecurity=false en las ocho tablas; pg_policies no devuelve políticas semánticas.

pg_auth_members: sin grants directos para administrator. La consulta pg_has_role devuelve acceso efectivo a todos los roles por ser superusuario; **no son membresías explícitamente concedidas**. Incluye capacidades de lectura/escritura global y ejecución de programas del servidor.

Los otros roles login encontrados no son superusuarios/bypass, pero ninguno tiene SELECT/INSERT en business_concepts. No hay rol Business Semantics reutilizable con privilegios efectivos adecuados. No se usó SET ROLE ni se adoptaron roles Evolution/LiteLLM/otros proyectos.

## Corrección mínima pendiente

La selección del rol runtime afecta el pool global; exige ventana DB/Auth coordinada, no un cambio silencioso desde este informe local.

Separar responsabilidad migración/administración privilegiada de operaciones runtime. Validar un rol runtime sin SUPERUSER/BYPASSRLS/CREATEROLE/CREATEDB ni propiedad de tablas, con grants acotados y autenticación legítima; conservar migraciones fuera del runtime.

Si se elige RLS, diseñar políticas explícitas para tablas padre e hijas, establecer el contexto tenant de forma confiable por transacción y probar accesos SQL negativos con rol no propietario/sin bypass. No habilitar RLS sobre las tablas actuales sin revisar consumidores y políticas.

Si se conserva aislamiento sólo en aplicación, documentar el riesgo residual y demostrar todas las rutas autenticadas, incluidos acceso directo por ID, versiones, propuestas, auditoría, modificaciones y caché. Inspeccionar WHEREs no satisface ese contrato.

No se implementó un pool paralelo, ni se cambió globalVar.py, modules/db/**, migraciones, Srv01 o servicios existentes. La autorización humana mínima es una ventana GLOBAL delimitada para seleccionar/validar el rol runtime y su integración; no se solicita cambiar producción.
