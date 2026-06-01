# ADR-002: navegacion contextual de Team360 Console

Estado: `aceptado`

Fecha: `2026-05-31`

## Contexto

Team360 Console debe servir a Team360, partners y clientes finales dentro de una arquitectura multi-organizacion. Una navegacion fija para todos expondria complejidad innecesaria y aumentaria el riesgo de confundir alcance visual con autorizacion real.

## Decision

Usar un unico App Shell adaptable. Derivar navegacion global y tabs de servicio desde:

```text
organization_type
role
effective_permissions
active_organization
active_workspace
contracted_services
available_modules
allowed_organization_scope
```

Los roles son perfiles iniciales de permisos, no la unica fuente de decision. Astro estructura rutas y layouts; Svelte 5 con Runes gestiona componentes interactivos y contexto de UI. El backend calcula permisos efectivos, modulos habilitados y scopes visibles.

## Consecuencias

- Team360, partners y clientes comparten shell sin compartir todas las opciones.
- La consola debe mostrar siempre organizacion, workspace, rol y tipo de acceso activos.
- La navegacion debe poder ocultar, deshabilitar, marcar solo lectura y mostrar badges.
- Los detalles tecnicos se reservan para Team360 o permisos especiales.
- `Mamá Mía 360` se usa como ejemplo configurable de partner, nunca como condicion hardcodeada.

## Fuera de alcance

- Implementar rutas, layouts o componentes.
- Crear navegacion funcional.
- Modificar DB.
- Definir diseño visual final.

## Referencias

- Guia extensa: `../ux/team360-console-navigation-model.md`
- Estrategia base: `../ux/team360-domains-and-console-strategy.md`
- Arquitectura viva: `../../lat.md/console-multi-organization.md`
