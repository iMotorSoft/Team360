# ADR-001: separacion de dominios y Team360 Console multi-organizacion

Estado: `aceptado`

Fecha: `2026-05-31`

## Contexto

Team360 necesita una presencia publica comercial y una plataforma privada para operar automatizaciones con IA. La consola debe servir a Team360, distribuidores regionales y clientes finales sin mezclar alcances ni datos.

`Mamá Mía 360` sera el primer distribuidor regional real para Israel, pero el producto debe soportar futuros partners sin reglas especiales.

## Decision

Separar dos dominios funcionales:

| Dominio | Responsabilidad |
| --- | --- |
| `team360.live` | Home publica institucional, comercial y de conversion |
| `console.team360.live` | Team360 Console privada, operativa y multi-organizacion |

Modelar Team360 como organizacion raiz. Modelar partners, clientes directos y clientes de partners como organizaciones relacionadas jerarquicamente. Usar workspaces como contextos operativos pertenecientes a una organizacion.

El frontend usara Astro para estructura, rutas y layouts, y Svelte 5 con Runes para componentes interactivos de consola. La autorizacion y el aislamiento multi-tenant pertenecen al backend.

## Consecuencias

- La home publica y la consola tienen arquitecturas de informacion distintas.
- La consola debe adaptar navegacion y datos al rol, permisos, organizacion y workspace activos.
- `Mamá Mía 360` se configura como `partner` con region `Israel`; no se hardcodea.
- La DB actual requiere una evolucion futura para organizaciones, jerarquia, membresias multi-workspace, servicios y alcance delegado.
- No se deben modificar migraciones existentes para simular soporte completo.

## Fuera de alcance

- Implementar pantallas o componentes.
- Crear rutas frontend.
- Aplicar migraciones.
- Definir pricing final.

## Referencias

- Guia extensa: `../ux/team360-domains-and-console-strategy.md`
- Arquitectura viva: `../../lat.md/console-multi-organization.md`
