# Identidades autenticadas

Las cuentas existen, pero no hay sesiones humanas legítimas disponibles ni un login/issuer autenticado Team360 demostrado en este checkout. No se inventaron sesiones ni tokens.

## Inventario real

Se consultaron sólo conteos y roles, sin emails, contraseñas, hashes, teléfonos o tokens.

| Ámbito | Usuarios activos | Administración organizacional observada | Sesión real disponible |
| --- | ---: | --- | --- |
| Telchi / telchi_dev | 2 | 1 organization_admin activo | No |
| Team360 / team360_admin_dev | 1 | organization_admin y otros roles activos | No |
| Otro tenant / team360_public_site | 2 | organization_admin y otros roles activos | No |

Existencia/RBAC en DB no acredita posesión de identidad. Tampoco una cuenta administrativa global demuestra automáticamente authority Telchi: BusinessConceptAdministration exige organization_admin de la organización del workspace.

## Mecanismo existente y faltante

El verificador PASETO es reutilizable, pero no constituye una ceremonia de login ni una prueba de identidad humana.

modules/console/auth.py verifica firma/issuer/tipo/expiración. business_semantics/cli.py recibe token por stdin y exige subject=user:user_id concordante. La shell y override no habilitan PASETO ni proporcionan clave pública/trust de issuer utilizable.

/api/console/bootstrap acepta user_id/workspace_id elegidos por caller, sin una sesión autenticada previa; está documentado como experimental DEV-only. No se llamó ese endpoint para emitir una identidad de prueba.

La búsqueda focalizada no localizó login/password enrollment ni integración de issuer humano; el inventario de columnas core_* no encontró columnas de password/auth/login. El [informe de provisioning](../../telchi/whatsapp-assistant-dev-live-v1/real_provisioning_report.md), sección 7, ya documenta este faltante. No usar metadata JSON como credential store.

## Intervención mínima

El bloqueo no se resuelve pidiendo cuatro contraseñas al usuario.

El responsable Console/Auth debe indicar el issuer/login legítimo existente y su canal privado de sesiones, si vive fuera de este checkout. Se requieren dos sujetos Telchi distintos, un sujeto de tenant B y un administrador Telchi Console; un admin puede ser uno de los dos sujetos Telchi si sus roles reales lo permiten.

Si no existe ese mecanismo, hace falta una ventana GLOBAL de Console/Auth para completar la pieza mínima compatible de enrollment/login/issuer, con validaciones negativas. Esta tarea no autoriza un sistema IAM paralelo ni impersonación por bootstrap.

Las cuentas ya existen: no ejecutar de nuevo live_cli, crear usuarios adicionales o elevar permisos para facilitar pruebas. No solicitar contraseñas personales por chat ni registrarlas en evidencia.
