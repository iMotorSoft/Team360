# Frontend Team360 - Home publica `team360.live`

Estado: implementado como primera version comercial publica.

Fecha: 2026-05-31.

## Objetivo

Crear la primera home comercial publica de Team360 en Astro, separada de la futura consola privada.

La pagina presenta una propuesta premium B2B, clara y consultiva para empresas que buscan automatizar procesos reales con IA sin incorporar complejidad innecesaria.

## Alcance implementado

- Ruta publica principal: `SrvRestAstroLS_v1/astro/src/pages/index.astro`.
- Layout publico independiente: `src/layouts/PublicMarketingLayout.astro`.
- Header y footer comerciales separados del futuro App Shell privado.
- CTA principal hacia solicitud de diagnostico por email.
- Acceso clientes enlazado hacia `https://console.team360.live/login`.
- Sin formulario conectado, backend, autenticacion, consola ni AG-UI funcional.

## Estructura de la home

1. Hero con propuesta central, CTAs y panel conceptual no tecnico.
2. Problemas operativos frecuentes.
3. Solucion Team360 en tres pasos.
4. Caminos de entrada sin precios ni promesas excesivas.
5. Casos de uso genericos.
6. Metodo de trabajo y control humano.
7. Diferenciacion frente a una herramienta de IA aislada.
8. Propuesta para partners regionales.
9. CTA final con contacto por email.
10. Footer con enlaces comerciales y acceso clientes.

## Decision de UX y copy

Mensaje central:

```text
Automatizacion con IA para procesos reales de negocio.
```

La promesa comercial se limita a diagnosticar, implementar por etapas y medir resultados. Se evita afirmar automatizacion total, reemplazo de personas o resultados inflados.

La home usa lenguaje de negocio:

- procesos;
- diagnostico;
- implementacion gradual;
- tableros y reportes;
- seguimiento;
- control humano;
- acompanamiento.

No expone lenguaje interno de arquitectura, workers, tenancy, permisos ni AG-UI.

## Direccion visual

- Fondo claro calido.
- Azul profundo como base institucional.
- Teal tecnologico como acento.
- Gradientes leves y grilla sutil solo en hero.
- Cards redondeadas con bordes suaves.
- Panel conceptual de tres etapas sin dashboards ficticios ni metricas infladas.
- Tipografia de sistema limpia, sin dependencias externas nuevas.
- Header sticky liviano y responsive.

## Archivos creados

- `SrvRestAstroLS_v1/astro/src/layouts/PublicMarketingLayout.astro`
- `SrvRestAstroLS_v1/astro/src/components/marketing/BrandMark.astro`
- `SrvRestAstroLS_v1/astro/src/components/marketing/MarketingHeader.astro`
- `SrvRestAstroLS_v1/astro/src/components/marketing/MarketingFooter.astro`
- `SrvRestAstroLS_v1/astro/src/components/marketing/SectionHeading.astro`
- `SrvRestAstroLS_v1/astro/src/components/marketing/HeroProcessVisual.astro`
- `SrvRestAstroLS_v1/astro/src/components/ui/LinkButton.astro`
- `SrvRestAstroLS_v1/astro/src/styles/marketing.css`

## Archivos modificados

- `SrvRestAstroLS_v1/astro/src/pages/index.astro`
- `SrvRestAstroLS_v1/astro/src/components/ui/README.md`
- `SrvRestAstroLS_v1/docs/README.md`
- `SrvRestAstroLS_v1/docs/status_actual.md`
- `docs/frontend/status_actual.md`

## Componentes usados

- `Badge.svelte`: eyebrow del hero.
- `LinkButton.astro`: wrapper UI nuevo para CTAs con semantica de enlace y variantes DaisyUI encapsuladas.
- Componentes Astro de marketing: composicion estatica sin hidratacion cliente innecesaria.

## Validacion ejecutada

Desde `SrvRestAstroLS_v1/astro/`:

```bash
corepack pnpm check
corepack pnpm build
corepack pnpm dev --host 127.0.0.1 --port 4321
```

Resultado:

- `astro check`: 0 errores, 0 warnings, 0 hints.
- `astro build`: OK, una ruta estatica `/index.html`.
- smoke browser desktop `1440px`: OK, sin overflow horizontal.
- smoke browser mobile `390px`: OK, sin overflow horizontal.
- estructura semantica: un `h1`, nueve secciones comerciales y navegacion accesible.
- sin `package-lock.json` ni `yarn.lock`.
- sin referencias publicas a Vertice360.
- sin referencias publicas hardcodeadas a partners concretos.
- `git diff --check -- SrvRestAstroLS_v1/astro`: OK.

## Pendientes

- Definir canal comercial real para reemplazar o confirmar `contacto@team360.live`.
- Incorporar favicon, imagen Open Graph y politica de privacidad cuando existan assets aprobados.
- Definir integracion futura del formulario de diagnostico.
- Ejecutar revision visual con branding final antes del despliegue productivo.
- Implementar despliegue publico de `team360.live` como tarea separada.
