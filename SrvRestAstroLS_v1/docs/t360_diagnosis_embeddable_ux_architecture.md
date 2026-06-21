# Team360 — Arquitectura UX para diagnósticos reutilizables y embebibles

## 1. Propósito

Team360 no debe tratar el diagnóstico como una experiencia exclusiva de la Home pública ni como una funcionalidad específica de Vera.

El diagnóstico debe evolucionar como una **capacidad de plataforma reusable**, capaz de ejecutar evaluaciones conversacionales y operativas sobre distintos dominios, proyectos y clientes.

El diagnóstico de automatización de Team360.live es el primer caso de uso real, pero no debe definir ni limitar la arquitectura general.

La plataforma debe permitir que, en el futuro, un cliente pueda disponer de diagnósticos propios para temas como:

* calificación comercial;
* relevamiento de necesidades;
* evaluación técnica;
* onboarding;
* soporte inicial;
* diagnóstico inmobiliario;
* recomendación de productos;
* auditoría operativa;
* evaluación educativa;
* troubleshooting;
* análisis de factibilidad;
* procesos internos específicos.

El mismo motor visual y conversacional debe poder utilizarse dentro de Team360 y también ser embebido en sitios externos.

---

# 2. Decisión de arquitectura

Team360 utilizará un modelo basado en:

```text
Definición de diagnóstico
        ↓
Runtime, políticas y conocimiento
        ↓
Contrato JSON estructurado
        ↓
Renderer Svelte genérico
        ↓
Adaptadores de distribución
```

Los adaptadores de distribución podrán incluir:

```text
- Home o Console Team360 en Astro
- iframe embebible
- Web Component
- futuro SDK JavaScript
```

El frontend no debe depender del dominio concreto del diagnóstico.

El LLM no genera HTML ni componentes visuales. El runtime devuelve información estructurada y el renderer decide cómo representarla mediante componentes controlados.

---

# 3. Principios fundamentales

## 3.1 El diagnóstico es agnóstico al dominio

Los componentes frontend no deben conocer conceptos específicos como:

* Vera;
* automatización;
* ventas;
* WhatsApp;
* Team360 Pack;
* Pack Flow;
* score de automatización;
* productos internos concretos.

Esos conceptos deben llegar como datos y configuración.

La capa visual reusable debe entender conceptos genéricos como:

```text
- título
- descripción
- estado
- opciones
- requisitos
- resultados
- recomendaciones
- pasos
- puntuación
- clasificación
- acciones
```

Un diagnóstico de automatización y uno inmobiliario deben poder usar el mismo renderer sin modificar los componentes.

---

## 3.2 El diagnóstico es agnóstico al sitio anfitrión

El renderer no debe depender estructuralmente de:

* una página Astro concreta;
* el layout de Team360;
* estilos globales externos;
* una ruta productiva específica;
* la presencia de Vera;
* el DOM completo de la página anfitriona.

Debe poder funcionar dentro de:

* una página Astro;
* una página HTML tradicional;
* WordPress;
* PHP;
* Laravel;
* React;
* Vue;
* Shopify;
* una intranet;
* un iframe;
* un Web Component;
* un contenedor standalone.

---

## 3.3 No se renderiza HTML libre

Se mantiene la decisión de seguridad:

* no usar `{@html}`;
* no usar `innerHTML`;
* no aceptar HTML generado por el LLM;
* no aceptar scripts;
* no aceptar componentes arbitrarios;
* no ejecutar acciones críticas desde contenido generado.

El backend entrega JSON validado.

Svelte renderiza únicamente componentes conocidos.

---

# 4. Contrato conceptual

El contrato general puede mantener esta forma:

```ts
export type T360AssistantTurnResponse = {
  assistant_text: string;
  conversation_state?: T360ConversationState;
  interaction_block?: T360InteractionBlock;
  diagnosis?: T360DiagnosisSnapshot;
};
```

Este contrato debe ser reusable para diferentes diagnósticos.

## 4.1 Assistant text

`assistant_text` contiene el mensaje conversacional.

Cuando existe `interaction_block`, el texto debe ser breve.

Ejemplo:

```json
{
  "assistant_text": "Ya tengo una orientación inicial. Elegí cómo querés seguir."
}
```

---

## 4.2 Interaction block

`interaction_block` describe una interacción visual conocida.

Bloques iniciales:

```text
- next_step_choice
- single_choice
- multi_choice
- missing_requirements
- product_fit_card
- diagnosis_action_card
```

Estos bloques deben seguir siendo genéricos.

En futuras iteraciones podrían incorporarse nuevos bloques, siempre mediante contratos versionados y renderers explícitos.

---

## 4.3 Diagnosis snapshot

El diagnóstico debe modelarse como un snapshot progresivo.

No debe depender de que la conversación llegue a un cierre definitivo.

Un diagnóstico puede estar:

```text
- not_ready
- preliminary
- usable
- complete
```

Debe evitarse que el tipo general incluya conceptos exclusivos del diagnóstico de automatización.

Una estructura más genérica puede ser:

```ts
export type T360DiagnosisSnapshot = {
  status: 'not_ready' | 'preliminary' | 'usable' | 'complete';

  title?: string;
  summary: string;

  score?: {
    value: number;
    max: number;
    label?: string;
  };

  classification?: {
    code: string;
    label: string;
    severity?: 'info' | 'success' | 'warning' | 'error';
  };

  findings?: T360Finding[];
  recommendations?: T360Recommendation[];
  missing_requirements?: T360Requirement[];
  next_actions?: T360Action[];
};
```

Ejemplo para automatización:

```json
{
  "classification": {
    "code": "requires_integration",
    "label": "Requiere integración",
    "severity": "warning"
  }
}
```

Ejemplo para calificación comercial:

```json
{
  "classification": {
    "code": "high_purchase_intent",
    "label": "Alta intención de compra",
    "severity": "success"
  }
}
```

El renderer no necesita conocer el significado interno de cada código.

---

# 5. Componentes frontend

La base de componentes debe permanecer genérica.

Componentes actuales:

```text
- T360InteractionRenderer.svelte
- T360ActionCard.svelte
- T360ChoiceGroup.svelte
- T360SingleChoice.svelte
- T360MultiChoice.svelte
- T360MissingRequirements.svelte
- T360ProductFitCard.svelte
- T360DiagnosisSummary.svelte
- T360StepList.svelte
- T360StatusBadge.svelte
- T360ActionButtons.svelte
```

## 5.1 Responsabilidades

### T360InteractionRenderer

Debe:

* recibir un bloque validado;
* delegar según `block.type`;
* no ejecutar lógica de negocio;
* no romper la UI ante un bloque desconocido;
* ofrecer fallback seguro.

### Componentes visuales

Deben:

* recibir datos tipados;
* emitir eventos;
* no acceder directamente al backend;
* no depender de rutas productivas;
* no depender de Vera;
* no asumir un diagnóstico concreto.

### Adapter de integración

La lógica que conecta eventos frontend con AG-UI, HTTP, SSE o cualquier runtime debe vivir fuera de los componentes.

---

# 6. Modos de distribución

## 6.1 Integración interna en Team360

El renderer puede utilizarse dentro de Astro para:

* Home pública;
* Console;
* laboratorios;
* configuración de proyectos;
* revisión de diagnósticos;
* onboarding de clientes.

Esta es la integración más directa, pero no debe ser la única.

---

## 6.2 Iframe embebible

El iframe debe considerarse la primera opción para distribución externa.

Ejemplo:

```html
<iframe
  src="https://app.team360.live/embed/diagnosis/example"
  title="Diagnóstico"
  loading="lazy"
></iframe>
```

Ventajas:

* aislamiento de CSS;
* aislamiento de JavaScript;
* compatibilidad amplia;
* integración sencilla en WordPress, PHP y HTML;
* control centralizado de versiones;
* menor riesgo de conflicto con themes y plugins;
* mejor aislamiento de seguridad.

El iframe puede comunicarse con la página anfitriona mediante `postMessage`.

Toda comunicación debe validar estrictamente el `origin`.

---

## 6.3 Web Component

En una fase posterior, Team360 podrá distribuir el diagnóstico como Web Component.

Ejemplo:

```html
<script src="https://cdn.team360.live/t360-diagnosis.js"></script>

<t360-diagnosis
  project="client-project"
  diagnosis="sales-assessment"
  locale="es"
></t360-diagnosis>
```

Ventajas:

* integración más natural;
* mejor adaptación al layout del sitio;
* personalización mediante atributos;
* compatibilidad con HTML, WordPress, PHP y frameworks modernos.

Consideraciones:

* Shadow DOM;
* aislamiento de estilos;
* lifecycle;
* versionado;
* autenticación;
* CORS;
* compatibilidad con navegadores;
* colisiones con el sitio anfitrión.

---

## 6.4 SDK JavaScript

Un SDK JavaScript puede evaluarse más adelante.

Ejemplo:

```html
<div id="team360-diagnosis"></div>

<script src="https://cdn.team360.live/t360-sdk.js"></script>

<script>
  Team360Diagnosis.mount({
    target: '#team360-diagnosis',
    projectId: 'project_123',
    diagnosisCode: 'sales_assessment'
  });
</script>
```

Esta opción brinda mayor flexibilidad, pero también aumenta:

* superficie de soporte;
* complejidad de integración;
* responsabilidad sobre el DOM;
* problemas de compatibilidad;
* manejo de versiones;
* riesgos de seguridad.

Orden recomendado:

```text
1. iframe
2. Web Component
3. SDK JavaScript, solo si existe necesidad real
```

---

# 7. Configuración del embed

El widget debe recibir configuración separada del contenido del diagnóstico.

Ejemplo:

```ts
export type T360EmbedConfig = {
  project_id: string;
  diagnosis_code: string;

  locale?: string;

  display_mode?:
    | 'inline'
    | 'modal'
    | 'floating'
    | 'fullscreen';

  theme?: T360ThemeConfig;

  api_base_url?: string;
  allowed_origin?: string;
};
```

La configuración no debe contener secretos privados.

El navegador debe utilizar identificadores públicos limitados o tokens temporales.

---

# 8. Tematización y estilos

DaisyUI puede seguir utilizándose dentro de Team360 y dentro de un iframe controlado.

Sin embargo, el renderer debe prepararse para funcionar sin depender de estilos globales del sitio anfitrión.

Se deben contemplar variables CSS como:

```css
--t360-primary;
--t360-primary-content;
--t360-background;
--t360-surface;
--t360-text;
--t360-muted-text;
--t360-border;
--t360-radius;
--t360-font-family;
--t360-shadow;
```

Estas variables permitirán personalizar:

* marca;
* colores;
* tipografía;
* bordes;
* radio de tarjetas;
* fondos;
* densidad visual.

La tematización no debe permitir inyectar CSS o HTML arbitrario.

---

# 9. Responsive basado en contenedor

Mobile-first continúa siendo obligatorio, pero no es suficiente utilizar únicamente media queries basadas en viewport.

Un diagnóstico embebido puede estar dentro de:

* una columna de 320 px;
* una sección central de 800 px;
* un modal;
* un sidebar;
* un chat flotante;
* una página completa.

Por ello, la UI debe considerar el ancho del contenedor.

Se recomienda evaluar:

* container queries;
* layouts flexibles;
* cards fluidas;
* botones adaptables;
* reducción progresiva de información secundaria;
* ausencia de tablas en espacios pequeños.

Los componentes deben poder trabajar correctamente en los modos:

```text
- inline
- modal
- floating
- fullscreen
```

---

# 10. Eventos públicos interoperables

Los componentes actuales pueden emitir eventos internos, pero la solución embebible debe definir también eventos públicos observables desde JavaScript estándar.

Ejemplos:

```text
t360:ready
t360:started
t360:answer-submitted
t360:interaction
t360:diagnosis-updated
t360:diagnosis-completed
t360:error
t360:resize
```

Ejemplo de consumo:

```js
const widget = document.querySelector('t360-diagnosis');

widget.addEventListener('t360:diagnosis-completed', event => {
  console.log(event.detail);
});
```

Los eventos públicos deben:

* tener nombres estables;
* estar versionados;
* incluir payload mínimo;
* evitar exponer datos internos innecesarios;
* no incluir credenciales;
* ser compatibles con Web Components e iframe.

Para iframe, los eventos podrán viajar mediante `postMessage`.

---

# 11. Multitenancy

Cada diagnóstico deberá asociarse como mínimo a:

```text
organization
workspace o project
diagnosis definition
diagnosis version
theme
knowledge scope
runtime policy
allowed domains
telemetry policy
```

Ejemplo:

```text
Cliente A
  └── Proyecto inmobiliario
       └── Diagnóstico de calificación de compradores

Cliente B
  └── Proyecto de soporte
       └── Diagnóstico inicial de incidencias
```

El renderer será el mismo.

Lo que cambia será:

* la definición;
* las preguntas;
* los bloques;
* el conocimiento;
* la política;
* el theme;
* la clasificación;
* los resultados;
* las acciones permitidas.

---

# 12. Seguridad para embeds

La arquitectura debe contemplar desde el inicio:

* validación de dominios permitidos;
* claves públicas limitadas por proyecto;
* tokens de sesión de corta duración;
* rate limiting;
* CORS;
* CSP;
* validación estricta de `postMessage`;
* no exponer secretos en HTML o JavaScript;
* sanitización del contenido;
* rechazo de HTML libre;
* versionado del contrato;
* límites de payload;
* aislamiento de sesiones;
* telemetry separada por cliente y proyecto;
* privacidad configurable;
* consentimiento cuando corresponda;
* prevención de replay;
* expiración de sesiones;
* bloqueo de acciones críticas no autorizadas.

El frontend nunca debe confiar en atributos del embed como fuente suficiente de autorización.

---

# 13. Separación de capas

La arquitectura debe conservar esta separación:

## Capa 1 — Definición del diagnóstico

Contiene:

* objetivos;
* preguntas;
* estados;
* categorías;
* reglas;
* resultados posibles;
* knowledge scope;
* políticas.

## Capa 2 — Runtime

Contiene:

* estado conversacional;
* interpretación de intención;
* selección de siguiente acción;
* generación de diagnóstico;
* validación del output;
* políticas de seguridad.

## Capa 3 — Contrato JSON

Contiene:

* texto;
* interaction blocks;
* diagnosis snapshot;
* conversation state;
* acciones permitidas.

## Capa 4 — Renderer

Contiene:

* componentes Svelte;
* accesibilidad;
* diseño responsive;
* render seguro;
* eventos frontend.

## Capa 5 — Adaptadores de entrega

Contiene:

* Astro;
* iframe;
* Web Component;
* SDK;
* AG-UI;
* SSE;
* HTTP;
* host communication.

---

# 14. Implicancias para la implementación actual

La implementación actual de `interaction_blocks` sigue siendo válida, pero debe revisarse con cuatro criterios adicionales:

## 14.1 Agnóstico al dominio

Los tipos y componentes no deben asumir automatización, ventas o Team360 Packs.

## 14.2 Agnóstico al host

Los componentes no deben depender del layout Astro ni de una página específica.

## 14.3 Estilos encapsulables

La UI debe poder funcionar dentro de iframe o Shadow DOM.

## 14.4 Eventos públicos interoperables

Las interacciones deben poder ser consumidas por JavaScript estándar y futuros adaptadores.

---

# 15. Fases recomendadas

## Fase A — Renderer genérico interno

Objetivo:

* estabilizar tipos;
* estabilizar guards;
* mejorar accesibilidad;
* validar bloques;
* mantener laboratorio Astro;
* evitar acoplamiento a Vera.

## Fase B — Embed por iframe

Objetivo:

* crear una ruta standalone;
* soportar configuración por proyecto y diagnóstico;
* auto-resize;
* comunicación por `postMessage`;
* validación de origen;
* theme básico;
* funcionamiento en WordPress y HTML.

## Fase C — Web Component

Objetivo:

* compilar renderer como custom element;
* encapsular estilos;
* exponer atributos;
* emitir eventos públicos;
* documentar instalación.

## Fase D — Configuración y multitenancy

Objetivo:

* asociar diagnosis definition;
* organization;
* workspace/project;
* theme;
* dominios permitidos;
* versiones;
* telemetry.

## Fase E — SDK opcional

Solo avanzar si iframe y Web Component no cubren necesidades reales de integración.

---

# 16. Criterio de éxito

La arquitectura será correcta cuando:

* el diagnóstico de automatización sea solo una configuración;
* pueda ejecutarse otro diagnóstico sin modificar componentes;
* el renderer funcione dentro y fuera de Team360;
* pueda embeberse en WordPress o PHP;
* el sitio anfitrión no pueda romper fácilmente la UI;
* la UI no pueda romper el sitio anfitrión;
* no exista HTML libre generado;
* los eventos sean interoperables;
* los estilos sean personalizables y encapsulables;
* cada cliente tenga aislamiento por proyecto;
* el contrato pueda versionarse;
* la seguridad no dependa del frontend.

---

# 17. Definición resumida

Team360 debe construir un motor visual genérico para diagnósticos conversacionales y operativos.

El diagnóstico de automatización de Team360.live será el primer caso de uso, pero la arquitectura debe permitir diagnósticos de cualquier temática y para distintos clientes.

El mismo motor deberá funcionar dentro de Team360 y también embebido en páginas externas mediante iframe, Web Component y, en una etapa posterior, un posible SDK JavaScript.

El runtime entregará JSON estructurado y validado. Svelte renderizará componentes conocidos. Los componentes serán agnósticos al dominio, al host y al backend concreto.

La solución deberá ser segura, reusable, multitenant, responsive por contenedor, tematizable y preparada para integrarse en WordPress, PHP y otras plataformas sin renderizar HTML libre ni exponer lógica crítica al navegador.
