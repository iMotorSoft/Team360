# Home Release Gate — Análisis de opciones

**Rama**: `feature/console-backend-core`
**Fecha**: 2026-06-15
**Propósito**: Definir gate de release público para la Home de Team360.

---

## 1. Archivos encontrados

| Ruta | Rol | Líneas | Estado |
|---|---|---|---|
| `src/pages/index.astro` | Home pública actual (raíz `/`) | 303 | Activa produciendo `dist/index.html` |
| `src/pages/t360.astro` | Home premium (ruta `/t360`) | 378 | Activa produciendo `dist/t360/index.html` |

Ambas usan `PublicMarketingLayout` como layout base.

---

## 2. Estado actual de `/`

La raíz es una página **consultiva**, con tono institucional-profesional. Incluye:

- Hero con **PublicVeraEntry** (componente Svelte `client:load`) que permite al usuario escribir su situación y obtener una respuesta inicial del diagnóstico.
- Secciones: problemas comunes, proceso de 3 pasos, caminos de entrada, casos de uso, método, partners, Vera chat, contacto email.
- CTA principal: **"Hablar con Vera"**.
- Sin referencias a T360 Pack/Task/Flow/Integrate.
- Sin disclaimer explícito sobre lead capture / WhatsApp handoff.
- Sin FAQ de objeciones.

La página **ya tiene diagnóstico conectado** vía `PublicVeraEntry` → `startPublicDiagnosis()` → `POST /api/diagnosis/start`. Esto es el wrapper público (`routes/diagnosis.py`) que actualmente responde con mock/preliminary.

---

## 3. Diferencias principales

| Aspecto | `/` (index.astro) | `/t360` (t360.astro) |
|---|---|---|
| **Tono** | Consultivo, institucional | Premium, directo, concreto |
| **CTA principal** | "Hablar con Vera" | "Probar diagnóstico" |
| **Diagnóstico** | Widget Vera funcional (`client:load`) | Sección estática + textarea (no conectado) |
| **Soluciones** | Caminos de entrada (5 items) | Packs temáticos (5 soluciones techniques) |
| **Tasks** | No explícito | Sí, 6 tasks concretas |
| **Modelo T360** | No mencionado | Pack / Task / Flow / Integrate |
| **Before/After** | No | Sí |
| **FAQ objeciones** | No | Sí (4 preguntas) |
| **Disclaimer lead/WhatsApp** | No | Sí explícito |
| **Partners** | Sección | Sección |
| **Contacto** | Email + Vera | Email + diagnosticador |
| **Hero visual** | SVG abstracto | Imagen real + gradiente |
| **Backend vivo** | Sí (PublicVeraEntry conectado) | No (solo mock visual) |
| **Complejidad técnica** | Svelte + JS runtime | HTML + CSS estático |

---

## 4. Opciones de release

### A. Dejar `/t360` como ruta candidata sin tocar `/`

**Pros:**
- Riesgo cero para la home actual.
- /t360 disponible para test A/B, preview, o compartir en campañas específicas.
- Sin cambios en el flujo de diagnóstico existente (Vera sigue funcionando).

**Contras:**
- /t360 no visible para usuarios que lleguen a `/`.
- Dos versiones pueden confundir si se enlazan sin criterio.

**Recomendación inmediata:** ✅ **Aceptable como estado actual.** No requiere cambios.

---

### B. Hacer redirect de `/` hacia `/t360`

**Pros:**
- Una sola cara visible público.
- Control centralizado del mensaje.

**Contras:**
- /t360 **no tiene el diagnóstico conectado** (no usa PublicVeraEntry). Perdería la funcionalidad de conversación inicial con Vera.
- /t360 es más específico (T360 Pack/Task/Flow/Integrate) que puede ser prematuro para visitantes nuevos.
- Redirect rompe enlaces existentes y cambia la experiencia esperada.

**Riesgo:** **ALTO.** No recomendar sin implementar el conector de diagnóstico en /t360.

---

### C. Reemplazar `/` por el contenido de `/t360`

**Pros:**
- Mensaje unificado.
- Visual premium en landing principal.

**Contras:**
- Pierde el diagnóstico funcional (PublicVeraEntry + Vera chat).
- Pierde flujo de entry paths y casos de uso actual.
- Requiere migrar el conector Vera a la nueva estructura.
- Cambio irreversible sin rollback cuidadoso.

**Riesgo:** **ALTO-EXTREMO.** No recomendar en esta etapa.

---

### D. Mantener ambas rutas con copy diferenciado

**Estado actual:** Esta es la opción que ya existe.

**Perfiles:**
- `/` → Visitante general, primera vez ("¿Qué es Team360?", "¿Cómo funciona?", "Hablar con Vera para entender").
- `/t360` → Visitante con más contexto, referido desde campaa específica o partner ("Ya sé qué ofrecen, quiero ver el detalle de packs").

**Pros:**
- Cada página optimizada para su audiencia.
- Sin riesgo de regresión.
- /t360 puede recibir tráfico controlado desde campañas.
- Diagnóstico funcional se mantiene en `/`.

**Contras:**
- Dos páginas para mantener.
- Posible confusión si el usuario encuentra ambas sin contexto.

**Recomendación:** ✅ **Opción más segura y ya implementada.**

---

## 5. Recomendación concreta

### Opción recomendada: **D (mantener ambas) + ajuste menor**

No mover / ni reemplazar. Mantener /t360 como ruta premium candidata. La home actual (/) ya tiene diagnóstico funcional (Vera), flujo de entrada claro y cobertura de casos de uso. /t360 suma una capa premium que puede activarse progresivamente.

### Próximos pasos sugeridos (no urgentes)

1. **Conectar diagnóstico en /t360** — /t360 tiene textarea estático; para reemplazar a / eventualmente, necesita el mismo widget Vera o un conector equivalente.
2. **Unificar CTA** — actualmente / dice "Hablar con Vera", /t360 dice "Probar diagnóstico". Podrían alinearse a "Empezar diagnóstico" en ambos.
3. **Agregar disclaimer a /** — la home actual no tiene la nota sobre lead/WhatsApp que /t360 ya incluye. Sería bueno agregarla.
4. **Medir tráfico** — antes de decidir fusión, medir qué flujo prefiere el usuario.

### ¿Tocar archivos ahora?

**No.** La opción D ya está implementada y es segura. Los pasos sugeridos pueden decidirse después sin urgencia.

---

## 6. Riesgos de cada opción

| Opción | Riesgo | Control |
|---|---|---|
| A (dejar /t360) | Bajo | Ninguno requerido |
| B (redirect) | Alto — pierde diagnóstico funcional | No recomendar |
| C (reemplazar) | Alto-extremo — pérdida de funcionalidad | No recomendar |
| D (ambas) | Bajo — mantenimiento de dos páginas | Ya implementado |

---

## 7. Resumen ejecutivo

La Home pública de Team360 tiene dos caras:
- **`/`** (index.astro) — funcional, consultiva, con Vera diagnóstico conectado.
- **`/t360`** (t360.astro) — premium, visual, con conceptos T360 pero sin diagnóstico conectado.

La opción más segura es **mantener ambas** (opción D, ya implementada). /t360 puede promoverse progresivamente cuando tenga el diagnóstico conectado. No se recomienda redirect ni reemplazo en esta etapa.

No se requieren cambios de código ahora. Si se decide avanzar en el futuro, los archivos a modificar serían:
- `src/pages/index.astro` — para agregar disclaimer y alinear CTA.
- `src/pages/t360.astro` — para conectar PublicVeraEntry o un conector de diagnóstico equivalente.
- `src/components/diagnosis/PublicVeraEntry.svelte` — si se requiere una versión adaptada para /t360.
