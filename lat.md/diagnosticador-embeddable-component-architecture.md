# Diagnosticador embeddable component architecture

## Proposito

Este documento es la fuente canonica para el contexto de componentes Team360.
Cuando el usuario escriba `contexto componentes`, el agente debe leer este
documento antes de proponer o modificar componentes, paquetes, estilos,
interaction blocks, adapters, tests E2E o estructura frontend vinculada al
Diagnosticador embebible.

El objetivo es guiar la extraccion progresiva del Diagnosticador embebible sin
iframe, respetando el estado real del repositorio y evitando sobrearquitectura.

## Decision

La primera etapa vive dentro de la app Astro actual:

```text
SrvRestAstroLS_v1/astro/src/lib/t360
```

No se debe crear ahora:

```text
/packages
pnpm-workspace.yaml en la raiz
package.json raiz funcional para workspaces
publicacion npm
paquetes separados para interaction blocks
paquetes separados para design tokens
```

La extraccion debe ser progresiva:

```text
DiagnosticadorCore.svelte
-> adapter Astro/Svelte
-> futuro JavaScript SDK o Web Component
```

`PublicVeraEntry.svelte` se mantiene como adapter de la Home publica y la zona
`/t360#vera` queda protegida: no se cambia estructura, layout, copy principal,
comportamiento ni ubicacion de forma destructiva.

## Estado actual que debe respetarse

El frontend actual vive en:

```text
SrvRestAstroLS_v1/astro
```

El namespace reutilizable ya existe en:

```text
SrvRestAstroLS_v1/astro/src/lib/t360
```

Piezas actuales relevantes:

```text
SrvRestAstroLS_v1/astro/src/components/diagnosis/PublicVeraEntry.svelte
SrvRestAstroLS_v1/astro/src/components/diagnosis/DiagnosisResult.svelte
SrvRestAstroLS_v1/astro/src/components/console/diagnosis/ConsoleDiagnosis.svelte
SrvRestAstroLS_v1/astro/src/lib/t360/diagnosis/
SrvRestAstroLS_v1/astro/src/lib/t360/interaction/
SrvRestAstroLS_v1/astro/src/components/global.js
```

`ConsoleDiagnosis.svelte` es otro flujo y otro contexto de producto. No debe
absorberse automaticamente en el Core embebible.

## Identidad del asistente

La identidad tecnica y la identidad visible son conceptos distintos:

```text
assistant_instance_id
= identidad tecnica estable

assistant_display_name
= nombre visible configurable

Diagnosticador
= nombre generico y fallback
```

Ejemplos:

```text
Team360 publico -> Vera
Cliente A -> Clara
Cliente B -> Asistente Comercial
Sin configuracion -> Diagnosticador
```

Prioridad del nombre visible:

```text
assistant_display_name del backend
-> assistantName como fallback temporal del adapter
-> Diagnosticador
```

El frontend no debe reemplazar permanentemente la identidad definida por el
backend.

## Estructura inicial recomendada

Esta es una guia de destino logico. No crear carpetas vacias sin necesidad.

```text
SrvRestAstroLS_v1/astro/src/
├─ components/
│  └─ diagnosis/
│     ├─ PublicVeraEntry.svelte
│     └─ DiagnosisResult.svelte
│
└─ lib/
   └─ t360/
      ├─ diagnosticador/
      │  ├─ DiagnosticadorCore.svelte
      │  ├─ index.ts
      │  ├─ api/
      │  ├─ state/
      │  │  ├─ conversation.svelte.ts
      │  │  └─ session.ts
      │  ├─ config/
      │  │  └─ defaults.ts
      │  ├─ events/
      │  │  └─ public.ts
      │  ├─ styles/
      │  │  ├─ tokens.css
      │  │  └─ core.css
      │  └─ types.ts
      │
      ├─ diagnosis/
      │  ├─ adapter.ts
      │  ├─ normalizer.ts
      │  ├─ markdown.ts
      │  └─ types.ts
      │
      └─ interaction/
         ├─ T360InteractionRenderer.svelte
         ├─ interaction blocks existentes
         ├─ types.ts
         ├─ guards.ts
         └─ events.ts
```

## Responsabilidades por capa

### DiagnosticadorCore.svelte

Debe contener:

- estado conversacional;
- conexion API configurable;
- render de mensajes;
- render de `DiagnosisResult`;
- render de `T360InteractionRenderer`;
- nombre dinamico del asistente;
- idioma;
- soporte RTL;
- eventos publicos;
- tema;
- estado de carga;
- errores;
- integracion con sesion.

No debe contener:

- layout marketing;
- header/footer;
- copy especifico de Team360;
- ejemplos de la Home;
- mailto de Team360;
- `id="vera"`;
- configuracion fija de una instancia;
- prompts;
- modelos;
- knowledge scopes arbitrarios;
- secretos;
- permisos;
- integraciones sensibles.

### PublicVeraEntry.svelte

Debe quedar como adapter de Team360 publico:

- configura a Vera;
- conserva ejemplos;
- conserva copy de la Home;
- conserva mailto;
- integra el Core cuando exista;
- mantiene compatibilidad con `/t360#vera`.

No debe seguir concentrando toda la logica interna a largo plazo.

### ConsoleDiagnosis.svelte

Debe permanecer separado. Es otro flujo y otro contexto de producto.

### Interaction blocks

Deben permanecer inicialmente en:

```text
src/lib/t360/interaction
```

Son compartidos internamente por el Diagnosticador. Solo deben extraerse a un
paquete independiente cuando un segundo producto real los consuma.

## Estado conversacional

La separacion recomendada es:

```text
state/
├─ conversation.svelte.ts
└─ session.ts
```

`conversation.svelte.ts` debe usar Svelte 5 runes y manejar:

- mensajes;
- sesion actual;
- locale;
- loading;
- error;
- nombre del asistente;
- interaction block;
- diagnosis result;
- turn count;
- lifecycle.

`session.ts` debe manejar:

- `sessionStorage`;
- key configurable;
- lectura;
- escritura;
- limpieza;
- compatibilidad SSR;
- no asumir `window` durante import.

La key no debe quedar fija como:

```text
team360.vera.session.v1
```

Debe poder derivarse de:

```text
assistant_instance_id
```

o ser configurable por adapter.

## Eventos publicos

La API publica futura usa la convencion:

```text
t360:*
```

Eventos iniciales:

```text
t360:ready
t360:conversation_started
t360:message_sent
t360:diagnosis_completed
t360:action_selected
t360:contact_requested
t360:error
```

Reglas:

- payload minimo;
- no incluir secretos, tokens ni datos sensibles innecesarios;
- compatibilidad con Svelte/Astro;
- compatibilidad futura con Web Component y SDK;
- `bubbles: true`;
- `composed: true`.

Los eventos internos actuales pueden mantenerse como implementacion interna. La
extraccion debe agregar un bridge hacia eventos publicos `t360:*` sin romper los
contratos existentes.

## Contrato publico inicial

Contrato conceptual:

```ts
type DiagnosticadorTheme = {
  primary?: string;
  secondary?: string;
  surface?: string;
  text?: string;
  textSecondary?: string;
  border?: string;
  radius?: string;
  fontFamily?: string;
  success?: string;
  warning?: string;
  error?: string;
};

type DiagnosticadorProps = {
  assistantInstanceId: string;
  assistantName?: string;
  apiBaseUrl: string;
  language?: "es" | "en" | "he";
  theme?: DiagnosticadorTheme;
  initialMessage?: string;
  sourcePage?: string;
  campaign?: string;
  compact?: boolean;
};
```

El Core distribuible no debe depender directamente de:

```text
components/global.js
```

`global.js` puede seguir siendo fuente de verdad para la Home Team360. El Core
debe recibir `apiBaseUrl` de forma explicita o mediante adapter.

## Temas y estilos

La estrategia visual acordada:

- el Core usa estilos propios;
- Tailwind y DaisyUI se usan solamente durante el build;
- el CSS final viaja con el componente o paquete;
- la pagina anfitriona no instala Tailwind ni DaisyUI;
- el cliente personaliza mediante variables CSS;
- no se exportan clases globales genericas;
- los estilos se encapsulan bajo una raiz Team360;
- el componente funciona aunque el host no tenga framework CSS.

Raiz visual:

```html
<div class="t360-diagnosticador" data-t360-root>
```

Variables iniciales:

```css
--t360-primary
--t360-primary-content
--t360-secondary
--t360-surface
--t360-text
--t360-text-secondary
--t360-border
--t360-radius
--t360-font-family
--t360-success
--t360-warning
--t360-error
--t360-shadow
```

Convenciones permitidas:

```css
.t360-diagnosticador .t360-button {}
.t360-diagnosticador .t360-card {}
.t360-diagnosticador .t360-badge {}
```

No exportar:

```css
.btn {}
.card {}
.badge {}
```

El host no debe necesitar:

- Tailwind;
- DaisyUI;
- Svelte;
- presets;
- plugins;
- `data-theme="team360"`.

## Reglas para futuros componentes

### Crear un producto nuevo

Cuando cambian:

- workflow principal;
- contrato API;
- lifecycle;
- experiencia completa;
- estado dominante;
- resultado de negocio.

Ejemplos:

```text
knowledge-search
document-intake
report-viewer
lead-capture
```

### Crear una variante

Cuando cambia solo:

- `assistant_instance_id`;
- `assistant_display_name`;
- knowledge scope;
- prompt;
- branding;
- idioma;
- initial message;
- configuracion.

Ejemplos:

```text
Diagnosticador de ventas
Diagnosticador de turnos
Diagnosticador administrativo
```

Son configuraciones del mismo Core. No duplicar componentes por cliente.

### Crear un interaction block

Cuando el backend necesita emitir una unidad visual nueva y tipada.

Cada block debe:

1. definir tipo;
2. agregar guard;
3. crear componente;
4. registrarse en renderer;
5. tener test;
6. documentar payload.

### Crear un adapter

Cuando cambia el host:

- Home Team360;
- Console;
- Astro/Svelte externo;
- Web Component;
- JavaScript SDK.

### Crear un paquete independiente

Solo cuando exista:

- consumo externo real;
- build independiente;
- versionado propio;
- publicacion;
- dos consumidores distintos;
- necesidad demostrada.

## Convenciones

Namespace:

```text
src/lib/t360/<producto>
```

Core:

```text
DiagnosticadorCore.svelte
```

Adapter publico:

```text
PublicVeraEntry.svelte
```

CSS:

```text
.t360-*
--t360-*
[data-t360-root]
```

Eventos:

```text
t360:*
```

Test IDs:

```text
t360-diagnosticador-*
t360-block-*
```

Paquete futuro:

```text
@team360/diagnosticador-svelte
```

No documentar todavia como paquetes necesarios:

```text
@team360/interaction-blocks
@team360/design-tokens
@team360/shared-contracts
```

## Evolucion

### Etapa 1 - Modularizacion interna

- Crear limites internos bajo `src/lib/t360/diagnosticador`.
- No crear workspace.
- No publicar.
- No mover interaction blocks.
- Mantener Home intacta.
- Extraer logica progresivamente.

### Etapa 2 - Paquete local

Cuando exista un primer consumidor externo:

```text
/packages/diagnosticador-svelte
```

Recien entonces:

- crear workspace;
- mover el Core;
- configurar library build;
- distribuir CSS;
- probar import local.

### Etapa 3 - Paquete privado/versionado

- SemVer;
- npm privado;
- changelog;
- contratos publicos estables;
- documentacion de integracion.

### Etapa 4 - Universal

Agregar Web Component o JavaScript mount SDK cuando haya hosts no Svelte/Astro
que lo justifiquen.

### Etapa 5 - Otros productos

Reutilizar estilos, interaction blocks, eventos, tipos, patterns y adapters.
Solo separar paquetes compartidos cuando un segundo producto lo justifique.

## Estrategia de pruebas

### Core

- render;
- estado;
- nombre dinamico;
- locale;
- RTL;
- eventos;
- errores;
- session restore;
- interaction blocks;
- diagnosis result.

### CSS

- host sin Tailwind;
- host sin DaisyUI;
- host con `.btn`, `.card`, `.badge` propias;
- dark mode;
- custom theme;
- font inherit;
- mobile;
- ancho reducido.

### Integracion Astro

- `/t360#vera` sigue funcionando;
- Vera permanece;
- no cambia layout;
- no cambia copy;
- no cambia flujo.

### Backend real

- start session;
- turn;
- `assistant_display_name`;
- interaction block;
- diagnosis result;
- CORS futuro.

### E2E

Usar backend y Astro reales levantados por scripts. Playwright automatiza el
navegador contra ese runtime con `PLAYWRIGHT_SKIP_WEBSERVER=1`. No depender del
`webServer` automatico de Playwright para cerrar funcionalidad runtime real.

## Riesgos y decisiones postergadas

Riesgos actuales:

- `PublicVeraEntry.svelte` concentra demasiada logica;
- algunos tipos siguen ligados a diagnostico de automatizacion;
- los eventos internos no usan todavia `t360:*`;
- `publicDiagnosis.ts` contiene contexto Team360 publico;
- el markdown debe mantenerse bajo politica estricta.

Decisiones postergadas:

- crear workspace raiz;
- crear `/packages`;
- publicar npm;
- separar interaction blocks;
- separar design tokens;
- crear shared contracts;
- crear Web Component o SDK.

Todas dependen de uso real externo o segundo consumidor.

## Regla de cierre

El Diagnosticador embebible debe evolucionar como un solo Core configurable,
adapters por host y variantes por `assistant_instance`. No duplicar componentes
por cliente y no fragmentar paquetes antes de tener consumidores reales.
