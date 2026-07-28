# Mamamia360 — Snippet embebible del Diagnosticador Vera

## Qué es

Componente JavaScript que inserta el Diagnosticador Vera de Team360 en una
página HTML o PHP externa. Realiza diagnóstico de factibilidad de procesos
sin requerir implementación técnica del distribuidor.

## Snippet

```html
<div id="team360-vera"></div>

<script
  src="https://team360.live/embed/vera-loader.js"
  data-client-id="mamamia360"
  data-locale="es"
  data-target="#team360-vera"
  data-assistant-name="Vera"
></script>
```

## Dónde pegarlo

- **HTML estático**: en el `<body>`, donde quieras que aparezca el chat.
- **PHP**: mismo snippet dentro del template.
- **WordPress**: bloque HTML o shortcode personalizado. Desactivar
  optimizadores de scripts que puedan alterar `data-*` attributes.

## Parámetros permitidos

| Atributo | Requerido | Default | Descripción |
|----------|-----------|---------|-------------|
| `data-client-id` | Sí | — | Identificador público del cliente (`mamamia360`) |
| `data-target` | No | `#team360-vera` | Selector CSS del contenedor |
| `data-locale` | No | `es` | Idioma (`es`, `en`, `he`) |
| `data-assistant-name` | No | `Vera` | Nombre visible del asistente |
| `data-compact` | No | `false` | Modo compacto (`true`/`false`) |
| `data-initial-message` | No | — | Mensaje inicial opcional |

## Dominio autorizado

```
https://mamamia360.com
```

El backend solo acepta requests desde este dominio. Si el dominio cambia,
solicitar actualización al equipo Team360.

## Qué NO debe modificar

- NO cambiar `data-client-id`.
- NO agregar `package_code`, `knowledge_scope_code`, `assistant_instance_code`
  ni ningún código interno en atributos o URL.
- NO intentar modificar el destino de los turnos de conversación.
- NO embeber secretos, tokens ni claves en la página.

## Cómo probar

1. Agregar el snippet en una página HTML simple.
2. Abrir la página en el navegador.
3. Escribir un mensaje como "recibo muchos email de facturación".
4. Vera responderá con preguntas secuenciales para completar el diagnóstico.
5. Al final, mostrará el diagnóstico de factibilidad.

## Qué mensaje esperar

Vera responde con:

- Preguntas secuenciales sobre el proceso.
- Bloques interactivos para seleccionar opciones.
- Diagnóstico de factibilidad al final.
- NO pregunta por API, webhooks, OAuth ni tokens de implementación.
- NO solicita datos técnicos prematuros.

## Contacto

Si el dominio cambia o hay problemas técnicos:

- Equipo Team360 — integracion@team360.live
- No modificar el snippet sin coordinar.
