# SAP Business One - Modelos de vision, costos y automatizacion desktop

Fecha: 2026-05-15
Proyecto: Team360
Objetivo: analisis tecnico no operativo
Alcance: seleccion preliminar de modelos para interpretar capturas de SAP Business One Desktop Client dentro de un esquema de automatizacion asistida.

## 1. Contexto

Team360 esta evaluando un servicio de automatizacion para clientes que operan SAP Business One Desktop Client en Windows.

El enfoque inicial no deberia depender de un modelo visual como mecanismo principal de control. Si SAP B1 expone controles mediante Microsoft UI Automation, esa debe ser la fuente primaria de estado y accion. La vision por captura queda como sensor auxiliar para casos donde UI Automation no alcance.

Arquitectura recomendada:

```text
DeepSeek V4 Flash
  orquestacion textual economica
        |
        v
Adaptador Windows / SAP B1
  Microsoft UI Automation
  OCR local
  captura + modelo visual
        |
        v
Acciones controladas
  click por control
  set value
  menu navigation
  hotkeys
  validacion posterior
```

## 2. Orden recomendado de lectura de estado

Para SAP Business One Desktop Client, el orden de fuentes debe ser:

1. Microsoft UI Automation.
2. OCR local.
3. Modelo visual economico.
4. Modelo visual superior o intervencion humana.

### Microsoft UI Automation

Si UI Automation detecta menus, dialogos, inputs, checkboxes, botones, valores y estado de controles, debe usarse antes que cualquier captura.

Ventajas:

- Menor costo.
- Mayor determinismo.
- Menor ambiguedad.
- Mejor trazabilidad.
- Permite acciones por control, no por coordenada.

### OCR local

OCR local puede cubrir errores, textos visibles, labels y mensajes simples sin costo de API.

Candidatos:

- Windows OCR / WinRT OCR.
- Tesseract.
- PaddleOCR.
- EasyOCR.

### Modelo visual

Usar solo cuando UI Automation y OCR no entreguen suficiente informacion. El modelo visual debe devolver salida compacta y estructurada, no una descripcion libre de pantalla.

Ejemplo de salida esperada:

```json
{
  "active_window": "SAP Business One - Pedido de cliente",
  "visible_text": [],
  "dialogs": [],
  "fields": [],
  "buttons": [],
  "errors": [],
  "recommended_next_step": "",
  "confidence": 0.0
}
```

## 3. Comparacion principal: gpt-5-nano vs Gemini 2.5 Flash-Lite

La comparacion relevante para capturas economicas es entre `gpt-5-nano` y `gemini-2.5-flash-lite`.

| Criterio | `gpt-5-nano` | `Gemini 2.5 Flash-Lite` |
| --- | --- | --- |
| Proveedor directo | OpenAI | Google |
| OpenRouter | No como modelo OpenAI directo | Si, `google/gemini-2.5-flash-lite` |
| Input imagen | Si | Si |
| Precio input publicado | USD 0.05 / 1M tokens | USD 0.10 / 1M tokens |
| Precio output publicado | USD 0.40 / 1M tokens | USD 0.40 / 1M tokens |
| Contexto | menor que Gemini 2.5 Flash-Lite | 1M tokens |
| Costo bruto para capturas | ventaja para `gpt-5-nano` | bajo, pero input 2x vs `gpt-5-nano` |
| Integracion multi-provider | menor si se usa OpenAI directo | mejor si el stack centraliza en OpenRouter |
| Uso recomendado | primera opcion si se acepta OpenAI directo | primera opcion si se quiere operar por OpenRouter |

Decision tecnica preliminar:

```text
Si se puede usar OpenAI directo:
  probar primero gpt-5-nano.

Si se quiere centralizar por OpenRouter:
  probar primero google/gemini-2.5-flash-lite.
```

La diferencia real debe medirse con capturas de SAP B1, no con benchmarks generales. El criterio principal no es solo precio por token, sino porcentaje de lecturas correctas sobre pantallas densas.

## 4. Otros modelos relevantes por OpenRouter

Modelos no OpenAI verificados como candidatos o complementos:

| Modelo | OpenRouter ID | Rol posible |
| --- | --- | --- |
| Gemini 2.5 Flash-Lite | `google/gemini-2.5-flash-lite` | candidato principal economico para capturas |
| Gemini 3.1 Flash Lite | `google/gemini-3.1-flash-lite` | fallback de mas calidad/costo |
| Qwen2.5-VL 7B | `qwen/qwen-2.5-vl-7b-instruct` | alternativa economica para pruebas |
| Qwen2.5-VL 32B | `qwen/qwen2.5-vl-32b-instruct` | alternativa intermedia |
| Qwen2.5-VL 72B | `qwen/qwen2.5-vl-72b-instruct` | alternativa de mayor calidad, menos clara en costo |
| DeepSeek V4 Flash | `deepseek/deepseek-v4-flash` | orquestador textual, no lector de capturas |

## 5. Rol de DeepSeek V4 Flash

DeepSeek V4 Flash no debe usarse como lector de capturas si no soporta vision en el flujo disponible. Su rol natural es:

- interpretar el estado textual recibido desde UI Automation, OCR o modelo visual;
- decidir la proxima accion;
- construir argumentos para tools cerradas;
- revisar logs y resultados;
- mantener bajo el costo de razonamiento recurrente.

DeepSeek no deberia ejecutar acciones libres por coordenadas. Debe invocar herramientas controladas.

Ejemplos de herramientas:

- `list_windows`
- `activate_window`
- `list_controls`
- `click_control`
- `set_text`
- `select_menu`
- `toggle_checkbox`
- `read_dialog`
- `read_grid`
- `press_hotkey`
- `capture_screen`
- `read_screen_with_vision`
- `wait_until`

## 6. Politica recomendada de ruteo

Flujo recomendado por cada paso de automatizacion:

```text
1. Leer estado por UI Automation.
2. Si el estado es suficiente, no capturar.
3. Si falta texto visible, ejecutar OCR local.
4. Si OCR no alcanza, enviar captura a modelo visual economico.
5. Si hay baja confianza o accion sensible, escalar a humano o modelo superior.
6. Ejecutar accion cerrada.
7. Esperar cambio.
8. Validar estado posterior.
9. Registrar evidencia.
```

Para operaciones sensibles, agregar aprobacion humana:

- creacion de documentos comerciales;
- contabilizacion;
- cambios de precios;
- modificaciones de maestro de articulos;
- movimientos de stock;
- acciones irreversibles o dificiles de revertir.

## 7. Benchmark minimo recomendado

Antes de decidir proveedor, preparar un set de 30 a 100 capturas reales de SAP B1.

Casos sugeridos:

- pantalla principal;
- menu abierto;
- formulario de pedido de cliente;
- formulario con campo activo;
- modal de error;
- dialogo de confirmacion;
- grilla con filas;
- status bar inferior;
- pantalla con texto chico;
- pantalla con campo obligatorio marcado;
- resultado posterior a una accion.

Mediciones:

- costo por captura;
- latencia;
- JSON valido;
- texto chico leido correctamente;
- deteccion de ventana activa;
- deteccion de dialogos;
- deteccion de errores;
- identificacion de campo activo;
- ausencia de controles inventados;
- calidad de `recommended_next_step`;
- porcentaje de escalaciones.

Modelos a comparar:

```text
gpt-5-nano
google/gemini-2.5-flash-lite
qwen/qwen-2.5-vl-7b-instruct
qwen/qwen2.5-vl-72b-instruct
```

## 8. Decision inicial recomendada

Para Team360, la decision inicial recomendada es:

```text
Orquestador:
  DeepSeek V4 Flash

Estado primario:
  Microsoft UI Automation

Texto visible barato:
  OCR local

Vision economica si se usa OpenAI directo:
  gpt-5-nano

Vision economica si se usa OpenRouter:
  google/gemini-2.5-flash-lite

Fallback:
  modelo visual superior o revision humana
```

Esta decision mantiene el costo bajo sin degradar el control operativo. Tambien evita que el sistema dependa de inferencia visual para acciones que pueden resolverse con informacion estructurada de Windows.

## 9. Riesgos

### Capturas como fuente principal

Riesgo: errores por resolucion, foco, idioma, tema visual, texto chico, tablas densas o ventanas superpuestas.

Mitigacion: usar UI Automation primero y vision solo como fallback.

### Acciones por coordenadas

Riesgo: clicks incorrectos por cambio de layout o ventana.

Mitigacion: priorizar acciones por control UIA. Coordenadas solo como ultimo recurso y con validacion posterior.

### Modelos baratos con baja consistencia

Riesgo: JSON invalido, controles inventados, lectura incorrecta de grillas.

Mitigacion: benchmark con capturas reales, schema estricto, confidence score y escalacion.

### Operaciones sensibles

Riesgo: impacto comercial o contable.

Mitigacion: aprobacion humana y herramientas cerradas con reglas por tipo de operacion.

## 10. Fuentes consultadas

- OpenAI pricing: https://developers.openai.com/api/docs/pricing#latest-models
- OpenAI vision: https://developers.openai.com/api/docs/guides/images-vision
- Gemini API pricing: https://ai.google.dev/gemini-api/docs/pricing
- OpenRouter Gemini 2.5 Flash-Lite: https://openrouter.ai/google/gemini-2.5-flash-lite/api
- OpenRouter Gemini 3.1 Flash Lite: https://openrouter.ai/google/gemini-3.1-flash-lite/api
- OpenRouter Qwen2.5-VL 7B: https://openrouter.ai/qwen/qwen-2.5-vl-7b-instruct/api
- OpenRouter Qwen2.5-VL 72B: https://openrouter.ai/qwen/qwen2.5-vl-72b-instruct/api
- OpenRouter DeepSeek V4 Flash: https://openrouter.ai/deepseek/deepseek-v4-flash/api
