# Team360 Frontend UI Policy

La interfaz de Team360 encapsula Tailwind CSS 4 y DaisyUI 5 detrás de componentes propios para evitar acoplamiento visual en las pantallas de negocio.

## Package manager

Esta sección establece la ejecución reproducible del frontend y la propiedad de sus archivos de dependencias.

- Usar `pnpm` para instalar dependencias y ejecutar scripts.
- Versionar `pnpm-lock.yaml` y declarar `packageManager`.
- No introducir `package-lock.json` ni `yarn.lock`.
- Autorizar scripts transitivos únicamente mediante configuración revisada por proyecto.

## Stack visual

Esta sección define cómo integrar el stack visual sin heredar configuración legacy ni convertir DaisyUI en una API pública.

```css
@import "tailwindcss";
@plugin "daisyui";
```

- Tailwind CSS 4 es la base utility-first.
- DaisyUI 5 acelera primitives internas.
- Los tokens y temas deben pertenecer a Team360.
- Las pantallas no deben dispersar clases DaisyUI como contrato visual.

## Componentes propios

Esta sección fija la frontera entre las pantallas de negocio y las librerías visuales subyacentes.

- Las pantallas consumen wrappers desde `src/components/ui/`.
- La lógica de negocio y transporte no pertenece a componentes UI base.
- Los wrappers exponen solo estados y variantes coherentes con su responsabilidad.
- Un cambio futuro de librería debe concentrarse principalmente dentro de esos wrappers.

## Fuentes canónicas

Esta política resume decisiones aprobadas y enlaza los documentos que conservan su justificación completa.

- `docs/adr/ADR-005-team360-pnpm-tailwind4-daisyui5-ui-policy.md`
- `docs/frontend/team360-package-manager-and-ui-policy.md`
- [[team360-frontend-base]]
