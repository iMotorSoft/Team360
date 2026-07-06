# Team360 Diagnosticador Embed v1 — Guía de instalación

## Para quién es

Esta guía es para técnicos que integran Vera/Diagnosticador Team360 en sitios
HTML, PHP o WordPress.

El Diagnosticador es un asistente conversacional embebible que se monta en una
página del cliente y se comunica con los servidores de Team360. No requiere
infraestructura del lado del cliente más allá de un contenedor HTML y un
script externo.

## Requisitos

1. `clientId` entregado por Team360.
2. Dominio/origin autorizado por Team360.
3. Sitio con HTTPS recomendado.
4. Permitir scripts desde `team360.live`.
5. Permitir requests a `team360.live/api`.
6. Un contenedor HTML donde montar el diagnosticador.

## Snippet recomendado con integrity

```html
<div id="team360-diagnosticador-root"></div>

<script
  src="https://team360.live/embed/team360-diagnosticador-loader.js"
  integrity="<loaderIntegrity desde https://team360.live/embed/team360-diagnosticador.manifest.json>"
  crossorigin="anonymous"
></script>

<script>
  window.Team360DiagnosticadorLoader.load({
    verifyEntryIntegrity: true
  }).then(function () {
    window.Team360Diagnosticador.mount("#team360-diagnosticador-root", {
      clientId: "CLIENT_ID_ENTREGADO_POR_TEAM360",
      apiBaseUrl: "https://team360.live/api",
      assistantName: "Vera",
      sessionStorageKey: "team360.embed.client.session.v1"
    });
  }).catch(function (error) {
    console.error("[Team360] No se pudo cargar el Diagnosticador", error);
  });
</script>
```

## Snippet simple compatible

Para casos donde el cliente técnico no quiere usar integrity al inicio:

```html
<div id="team360-diagnosticador-root"></div>

<script src="https://team360.live/embed/team360-diagnosticador-loader.js"></script>

<script>
  window.Team360DiagnosticadorLoader.load().then(function () {
    window.Team360Diagnosticador.mount("#team360-diagnosticador-root", {
      clientId: "CLIENT_ID_ENTREGADO_POR_TEAM360",
      apiBaseUrl: "https://team360.live/api",
      assistantName: "Vera"
    });
  });
</script>
```

> El modo simple existe por compatibilidad. El modo recomendado para producción
> es con integrity.

## HTML estático

Ejemplo completo mínimo:

```html
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <title>Demo Team360 Diagnosticador</title>
</head>
<body>
  <h1>Diagnóstico Team360</h1>
  <div id="team360-diagnosticador-root"></div>

  <!-- snippet Team360 aquí -->
  <script
    src="https://team360.live/embed/team360-diagnosticador-loader.js"
    integrity="<loaderIntegrity desde manifest>"
    crossorigin="anonymous"
  ></script>
  <script>
    window.Team360DiagnosticadorLoader.load({
      verifyEntryIntegrity: true
    }).then(function () {
      window.Team360Diagnosticador.mount("#team360-diagnosticador-root", {
        clientId: "CLIENT_ID_ENTREGADO_POR_TEAM360",
        apiBaseUrl: "https://team360.live/api",
        assistantName: "Vera",
        sessionStorageKey: "team360.embed.client.session.v1"
      });
    });
  </script>
</body>
</html>
```

## PHP tradicional

```php
<?php
$team360ClientId = 'CLIENT_ID_ENTREGADO_POR_TEAM360';
?>
<div id="team360-diagnosticador-root"></div>

<script
  src="https://team360.live/embed/team360-diagnosticador-loader.js"
  integrity="<loaderIntegrity desde manifest>"
  crossorigin="anonymous"
></script>

<script>
  window.Team360DiagnosticadorLoader.load({
    verifyEntryIntegrity: true
  }).then(function () {
    window.Team360Diagnosticador.mount("#team360-diagnosticador-root", {
      clientId: <?php echo json_encode($team360ClientId); ?>,
      apiBaseUrl: "https://team360.live/api",
      assistantName: "Vera",
      sessionStorageKey: "team360.embed.client.session.v1"
    });
  });
</script>
```

> El `clientId` es público. No colocar secrets en PHP ni en JavaScript.

## WordPress — Bloque HTML

En Gutenberg, Elementor, Divi u otros builders, pegar el snippet en un bloque
HTML personalizado.

> Algunos plugins de seguridad, minificación o caché pueden mover o alterar
> scripts. Si el snippet con integrity falla, revisar optimizadores.

## WordPress — Shortcode/plugin mínimo conceptual

Este ejemplo es una referencia técnica, no un plugin final para producción.

```php
<?php
/**
 * Plugin Name: Team360 Diagnosticador Embed
 * Description: Inserta el Diagnosticador Team360 mediante shortcode.
 * Version: 0.1.0
 */

function team360_diagnosticador_shortcode($atts) {
    $atts = shortcode_atts(array(
        'client_id' => 'CLIENT_ID_ENTREGADO_POR_TEAM360',
    ), $atts);

    ob_start();
    ?>
    <div id="team360-diagnosticador-root"></div>
    <script
      src="https://team360.live/embed/team360-diagnosticador-loader.js"
      integrity="<loaderIntegrity desde manifest>"
      crossorigin="anonymous"
    ></script>
    <script>
      window.Team360DiagnosticadorLoader.load({
        verifyEntryIntegrity: true
      }).then(function () {
        window.Team360Diagnosticador.mount("#team360-diagnosticador-root", {
          clientId: <?php echo json_encode($atts['client_id']); ?>,
          apiBaseUrl: "https://team360.live/api",
          assistantName: "Vera",
          sessionStorageKey: "team360.embed.client.session.v1"
        });
      });
    </script>
    <?php
    return ob_get_clean();
}
add_shortcode('team360_diagnosticador', 'team360_diagnosticador_shortcode');
```

Uso:

```
[team360_diagnosticador client_id="CLIENT_ID_ENTREGADO_POR_TEAM360"]
```

> Este ejemplo es una referencia mínima. Para producción, el cliente puede
> adaptarlo a su theme/plugin.

## Parámetros permitidos

| Parámetro              | Público | Requerido | Descripción                             |
| ---------------------- | ------: | --------: | --------------------------------------- |
| `clientId`             |      Sí |        Sí | Identificador público del cliente embed |
| `apiBaseUrl`           |      Sí |        Sí | URL de API Team360                      |
| `assistantName`        |      Sí |        No | Nombre visible del asistente            |
| `sessionStorageKey`    |      Sí |        No | Key para aislar sesión                  |
| `verifyEntryIntegrity` |      Sí |        No | Activa verificación del asset interno   |

## Parámetros prohibidos

Estos datos se resuelven server-side desde Team360 y nunca deben estar en el
sitio del cliente:

- `hmac_secret`
- `organization_code`
- `workspace_code`
- `package_code`
- `knowledge_scope_code`
- `assistant_instance_code`
- `allowed_origins`

## Alta de cliente (equipo Team360)

1. Crear `clientId`.
2. Configurar `allowed_origins` exactos.
3. Asociar el `clientId` al contexto de Team360 correspondiente.
4. Confirmar que el dominio final usa HTTPS.
5. Entregar snippet y `clientId`.
6. Validar desde el dominio real.

## Troubleshooting

| Problema | Posible causa |
| -------- | ------------- |
| No aparece el componente | El div contenedor no existe o el script no se cargó |
| Error de integrity | El valor de `integrity` en el `<script>` no coincide con el manifest actual |
| Error 403 en embed/auth | El origin del sitio no está autorizado en `allowed_origins` |
| Error CORS | El navegador bloquea requests a `team360.live` desde el origin del cliente |
| WordPress mueve/minifica scripts | Plugins de caché o minificación pueden alterar o diferir scripts |
| CSP bloquea `team360.live` | La política Content-Security-Policy debe incluir `team360.live` |
| Caché conserva loaderIntegrity viejo | Invalidar caché del navegador o CDN tras actualizar el manifest |
| El dominio con www no coincide | `www.ejemplo.com` y `ejemplo.com` son origins distintos |
| HTTPS vs HTTP | El sitio en HTTP puede tener problemas mixtos de contenido |

## Checklist del técnico del cliente

- [ ] Pegué el div contenedor.
- [ ] Pegué el script loader.
- [ ] Usé el `clientId` correcto.
- [ ] El dominio fue autorizado por Team360.
- [ ] No agregué `hmac_secret` ni datos internos.
- [ ] No hay plugins que alteren el script.
- [ ] La consola del navegador no muestra error de CORS/integrity.

## Checklist Team360

- [ ] `clientId` creado.
- [ ] `allowed_origins` configurados.
- [ ] `hmac_secret` server-side.
- [ ] Tenant/scope server-side.
- [ ] Snippet entregado.
- [ ] Manifest accesible.
- [ ] Loader accesible.
- [ ] Prueba auth/turn OK.

## Recursos

- Manifest: `https://team360.live/embed/team360-diagnosticador.manifest.json`
- Loader: `https://team360.live/embed/team360-diagnosticador-loader.js`
- Asset: `https://team360.live/embed/team360-diagnosticador.js`
- API: `https://team360.live/api`

## Limitaciones conocidas v1

- Sin package npm.
- Sin Web Component nativo.
- Sin Shadow DOM / CSS encapsulado final.
- Sin eventos públicos `t360:*` definitivos.
- Sin plugin WordPress productivo publicado en marketplace.
- Sin publicación en CDN externo.
