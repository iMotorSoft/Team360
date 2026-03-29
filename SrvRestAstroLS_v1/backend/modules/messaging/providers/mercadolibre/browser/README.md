# Mercado Libre Browser Lab

Helpers minimos para abrir un browser persistente con Playwright y reutilizar sesion entre corridas.

El alcance actual cubre solo:

- home de Mercado Libre
- summary de cuenta como ruta real de inspeccion
- preguntas del vendedor como ruta real de inspeccion pre-venta
- login manual
- deteccion conservadora de sesion
- inspeccion de home autenticada para descubrir affordances reales
- inspeccion de summary de cuenta para descubrir affordances reales
- inspeccion de preguntas del vendedor para descubrir affordances reales
- deteccion heuristica de wizard, onboarding, modal blocking y banner-like overlays
- acceso basico a inbox con heuristicas simples
- inspeccion puntual del DOM del inbox para ajustar selectores
- screenshot, storage state y reportes de debug en `runtime/`

No incluye lectura detallada de hilos ni respuestas.
