# Team360 Console - App Shell y sistema de layouts base

Estado: `aprobado como base UX/frontend inicial`

Fecha: `2026-05-31`

Audiencia: producto, UX/UI, frontend y backend.

Referencias:

- Estrategia de dominios: `team360-domains-and-console-strategy.md`
- Navegacion contextual: `team360-console-navigation-model.md`
- ADR resumido: `../adr/ADR-003-team360-console-app-shell-and-layout-system.md`
- Arquitectura viva: `../../lat.md/console-multi-organization.md`

## Resumen ejecutivo

`console.team360.live` debe usar un unico App Shell adaptable para Team360, partners y clientes finales. El shell mantiene una estructura estable, mientras la navegacion, profundidad tecnica, acciones y datos visibles cambian segun organizacion activa, workspace, permisos efectivos, modulos habilitados, servicios contratados y arbol autorizado.

No se deben crear consolas separadas por rol. Tampoco corresponde construir un panel administrativo generico con todas las opciones visibles. Team360 Console debe presentar primero servicios, resultados, alertas y acciones relevantes, y revelar profundidad tecnica de forma progresiva.

Astro.js estructura rutas, layouts, paginas base y carga inicial. Svelte 5 con Runes concentra interactividad, estado derivado y componentes dinamicos de consola.

## Alcance

Este documento define:

- App Shell;
- layouts base;
- patrones visuales y estructurales;
- responsabilidades de Astro y Svelte;
- estados de UI;
- comportamiento responsive;
- recomendaciones para diseno y frontend.

No define:

- implementacion final;
- estetica visual definitiva;
- base de datos;
- APIs definitivas;
- componentes codificados;
- rutas reales;
- migraciones;
- configuracion de build.

## Principios del App Shell

1. Usar un unico App Shell adaptable.
2. Mostrar siempre el contexto activo.
3. Derivar navegacion desde permisos, modulos y contexto.
4. Priorizar resultados y acciones antes que complejidad tecnica.
5. Revelar profundidad tecnica de forma progresiva.
6. Permitir que Team360 vea capas tecnicas profundas segun permisos.
7. Permitir que partners vean solo su red autorizada.
8. Mostrar a clientes finales servicios, resultados y reportes.
9. Mantener workers fuera del protagonismo para clientes.
10. Respaldar todo ocultamiento frontend con validacion backend.

## Estructura conceptual del App Shell

```text
App Shell
|-- Sidebar contextual
|-- Topbar
|-- Workspace / Organization switcher
|-- Breadcrumbs
|-- Main content area
|-- Right panel opcional
|-- Notification center
|-- Command/search opcional
|-- User/account menu
`-- Global loading/error boundary
```

| Elemento | Funcion |
| --- | --- |
| Sidebar contextual | Navegacion global derivada desde capacidades |
| Topbar | Contexto activo, accesos globales y advertencias |
| Workspace / Organization switcher | Cambio explicito de contexto autorizado |
| Breadcrumbs | Ubicacion jerarquica dentro de la consola |
| Main content area | Contenido principal de la ruta activa |
| Right panel opcional | Actividad, ayuda, detalle o acciones secundarias |
| Notification center | Pendientes y eventos visibles para el contexto |
| Command/search opcional | Busqueda y accesos rapidos autorizados |
| User/account menu | Perfil, preferencias, ayuda y sesion |
| Global loading/error boundary | Estados seguros cuando falla contexto o carga |

## Wireframe estructural

```text
+------------------------------------------------------------------------+
| Topbar: contexto | search opcional | acciones | notificaciones | cuenta |
+-----------------------+------------------------------------------------+
| Sidebar contextual    | Breadcrumbs                                    |
|                       +------------------------------------------------+
| grupos y modulos      | Main content area                              |
| permitidos            |                                                |
|                       |                                                |
|                       |                                  Right panel   |
|                       |                                  opcional       |
+-----------------------+------------------------------------------------+
```

## Sidebar contextual

La sidebar presenta navegacion derivada. No debe codificarse como una lista fija por rol.

Debe soportar:

- grupos;
- items y subitems;
- badges;
- estados `disabled`;
- estados `read_only`;
- indicadores de configuracion pendiente;
- colapso en desktop;
- drawer en tablet y mobile;
- navegacion global;
- accesos contextuales por servicio cuando corresponda.

### Grupos sugeridos para Team360

| Grupo | Modulos posibles |
| --- | --- |
| Operacion | Inicio, cola de trabajo, ejecuciones, alertas, tareas |
| Red comercial | Organizaciones, distribuidores, clientes, workspaces |
| Automatizacion | Servicios, workers, integraciones |
| Resultados | Dashboards, reportes |
| Administracion | Usuarios, roles y permisos, facturacion, soporte |
| Sistema | Auditoria, configuracion |

### Grupos sugeridos para Partner

| Grupo | Modulos posibles |
| --- | --- |
| Mi operacion | Inicio, mis servicios |
| Clientes | Mis clientes, leads, servicios de mis clientes |
| Resultados | Resultados, reportes |
| Equipo | Usuarios y accesos permitidos |
| Soporte | Solicitudes, configuracion, branding habilitado |

### Grupos sugeridos para Cliente

| Grupo | Modulos posibles |
| --- | --- |
| Mis servicios | Inicio, servicios contratados, automatizaciones |
| Resultados | Resultados, reportes, archivos |
| Atencion | Alertas, tareas |
| Soporte | Equipo, soporte, configuracion permitida |

### Regla de sidebar

```text
sidebar_items =
  navigation_registry
  filtered by effective_permissions
  filtered by enabled_modules
  filtered by active_workspace
  filtered by organization_type
  enriched with scoped badges
```

## Topbar

La topbar debe mostrar:

- organizacion activa;
- workspace activo;
- rol efectivo o modo de operacion;
- indicador de acceso propio o delegado;
- buscador o command palette opcional;
- notificaciones;
- acciones rapidas autorizadas;
- usuario actual.

Cuando el usuario observa datos de un cliente o suborganizacion, debe existir una advertencia visible:

```text
Viendo: Cliente X
Workspace: Operacion principal
Acceso delegado por: Partner Y
```

Para Team360:

```text
Viendo: Cliente X
Origen: cliente directo o cliente gestionado por Partner Y
```

## Workspace / Organization switcher

El selector debe ser accesible, buscable y seguro.

Debe:

- mostrar solo organizaciones y workspaces autorizados;
- reflejar jerarquia;
- diferenciar Team360, partners y clientes;
- mostrar contextos recientes;
- admitir busqueda;
- indicar estado del workspace;
- indicar alertas relevantes sin filtrar informacion ajena;
- confirmar cambios cuando exista una accion sensible en progreso;
- validar el nuevo contexto contra backend.

Ejemplo conceptual:

```text
Team360
|-- Clientes directos
`-- Partners
    `-- Mamá Mía 360
        `-- Clientes Mamá Mía 360
```

`Mamá Mía 360` es solo un ejemplo configurable de `partner`. No debe existir logica frontend condicionada por su nombre, region o posicion inicial.

## Breadcrumbs

Los breadcrumbs deben reflejar profundidad:

```text
Organizacion > Workspace > Modulo > Servicio > Vista
```

Ejemplo:

```text
Team360 > Mamá Mía 360 > Cliente X > Servicio Leads > Ejecuciones
```

Reglas:

- no reemplazan al switcher;
- deben ser compactos;
- ayudan a evitar operaciones en un contexto incorrecto;
- deben preservar trazabilidad cuando se profundiza desde dashboard a evidencia.

## Main content area

El area principal debe soportar patrones reutilizables:

- dashboard;
- lista o tabla;
- detalle;
- formulario o configuracion;
- reporte o dashboard embebido;
- detalle de servicio;
- detalle tecnico de worker;
- empty state;
- loading state;
- error state;
- permission denied.

La pagina debe mantener una jerarquia consistente:

```text
Breadcrumbs
Page header
Contextual actions
Status / summary
Primary content
Secondary detail
```

## Right panel opcional

El panel derecho puede usarse para:

- actividad reciente;
- detalles rapidos;
- ayuda contextual;
- notas internas;
- timeline de servicio;
- alertas;
- tareas pendientes;
- soporte;
- auditoria resumida.

Reglas:

- es opcional;
- no debe bloquear la operacion principal;
- debe poder cerrarse;
- no debe contener acciones criticas sin confirmacion;
- debe respetar permisos y scope;
- en pantallas estrechas se convierte en drawer o vista separada.

## Notification center

El centro de notificaciones puede incluir:

| Tipo | Ejemplo |
| --- | --- |
| Alerta tecnica | Worker con fallas repetidas |
| Alerta de negocio | Resultado fuera de umbral |
| Tarea pendiente | Revision manual requerida |
| Reporte generado | Exportable disponible |
| Fallo de worker | Run bloqueado o expirado |
| Aprobacion requerida | Accion sensible pendiente |
| Soporte | Respuesta o escalamiento |
| Facturacion | Vencimiento o incidencia, si corresponde |

Reglas:

- filtrar por permisos y contexto;
- mostrar severidad y estado;
- evitar filtrar datos de otro tenant en badges;
- permitir navegar a evidencia autorizada;
- distinguir leido, pendiente y resuelto.

## Command / search opcional

Una command palette puede mejorar operacion experta, pero no es requisito inicial.

Puede permitir:

- buscar clientes autorizados;
- cambiar workspace;
- buscar servicios;
- abrir reportes;
- acceder a tareas;
- ejecutar acciones rapidas seguras.

No debe:

- saltar controles de permisos;
- revelar nombres fuera del scope;
- ejecutar acciones sensibles sin confirmacion.

## Patrones de layout

### A. Dashboard ejecutivo

Uso:

- inicio Team360;
- inicio partner;
- inicio cliente.

Incluye:

- cards de resumen;
- KPIs;
- servicios activos;
- alertas;
- resultados recientes;
- actividad;
- proximos pasos.

La profundidad se adapta al contexto. Team360 observa red y operacion; partner observa su red; cliente observa prestaciones y resultados.

### B. Lista / tabla operativa

Uso:

- clientes;
- servicios;
- workers;
- ejecuciones;
- reportes;
- usuarios;
- integraciones.

Incluye:

- filtros;
- busqueda;
- estados;
- acciones por fila;
- paginacion;
- exportacion cuando corresponda;
- columnas configurables en una fase posterior;
- seleccion multiple solo donde sea segura.

Responsive:

- desktop: tabla;
- tablet: tabla reducida;
- mobile: cards o filas resumidas con drill-down.

### C. Vista detalle

Uso:

- cliente;
- partner;
- servicio;
- worker;
- ejecucion;
- reporte.

Incluye:

- encabezado con estado;
- metadata clave;
- tabs;
- resumen;
- acciones principales;
- actividad;
- permisos;
- right panel opcional.

### D. Vista de servicio contratado

Tabs sugeridas:

| Tab | Uso |
| --- | --- |
| Resumen | Objetivo, estado, KPIs y pendientes |
| Configuracion | Parametros permitidos |
| Ejecuciones | Runs visibles |
| Resultados | Salidas comprensibles |
| Reportes | Consultas o exportables |
| Alertas | Eventos relevantes |
| Archivos | Entradas, salidas y evidencia |
| Historial | Actividad autorizada |
| Soporte | Solicitudes contextualizadas |

No todas las tabs son visibles para todos. Team360 puede acceder a mayor profundidad; partner recibe configuracion delegada; cliente ve resultados y acciones comprensibles.

### E. Vista tecnica de worker

Solo para Team360 o permisos tecnicos expresos.

Tabs sugeridas:

| Tab | Uso |
| --- | --- |
| Resumen | Estado, tipo y capacidades |
| Configuracion | Parametros tecnicos permitidos |
| Runs | Ejecuciones relacionadas |
| Logs | Logs resumidos y seguros |
| Credenciales / Integraciones | Referencias autorizadas, nunca secretos |
| Alertas | Incidentes |
| Costos / consumo | Metricas si aplican |
| Auditoria | Cambios y actividad |

Los clientes no deben acceder por defecto a esta vista.

### F. Formulario / configuracion

Uso:

- crear usuario;
- configurar servicio;
- editar integracion;
- asignar paquete;
- editar permisos.

Debe incluir:

- validacion clara;
- modo lectura;
- permisos visibles;
- confirmacion para acciones sensibles;
- advertencia de impacto;
- auditoria cuando corresponda;
- prevencion de cambios peligrosos;
- feedback de guardado.

### G. Empty states

| Estado | Mensaje esperado | Proximo paso |
| --- | --- | --- |
| Sin servicios contratados | Todavia no hay servicios activos | Contactar comercial o admin |
| Sin reportes generados | No existen reportes para el periodo | Revisar filtros o generar reporte |
| Sin ejecuciones | El servicio aun no registra runs | Ver configuracion o esperar primera ejecucion |
| Sin clientes cargados | El partner aun no tiene clientes | Iniciar onboarding si tiene permiso |
| Sin permiso de modulo | No tiene acceso a esta seccion | Volver o contactar admin |
| Workspace sin configurar | Falta configuracion inicial | Continuar onboarding o solicitar soporte |

Un empty state debe explicar que ocurre y ofrecer el siguiente paso permitido.

### H. Loading / skeleton states

Debe haber estados diferenciados para:

- bootstrap inicial;
- cambio de organizacion;
- cambio de workspace;
- navegacion;
- dashboard;
- tablas;
- detalle;
- panel lateral.

Reglas:

- no mezclar datos del contexto anterior con el nuevo;
- mantener estructura visual estable;
- cancelar o descartar respuestas obsoletas;
- indicar carga prolongada cuando supere el tiempo esperado.

### I. Error states

| Error | Tratamiento UX |
| --- | --- |
| Permisos | Mensaje seguro y retorno |
| Carga de contexto | Bloquear datos y solicitar reintento o seleccion |
| Worker | Mostrar afectacion y escalamiento autorizado |
| Integracion | Mostrar estado, evidencia segura y soporte |
| Dashboard parcial | Mantener widgets disponibles y marcar fallos |
| Sesion expirada | Solicitar reautenticacion sin perder contexto posible |

### J. Permission denied

Debe ser claro y seguro:

- no revelar informacion sensible;
- indicar falta de acceso;
- permitir volver;
- ofrecer contacto con admin o soporte cuando corresponda;
- registrar intento si la ruta es sensible;
- no depender solo de ocultamiento en sidebar.

## Global loading/error boundary

El shell necesita un boundary global para:

- bootstrap fallido;
- sesion expirada;
- contexto invalido;
- workspace retirado;
- perdida de permisos;
- carga parcial.

Regla:

```text
No renderizar datos privados hasta validar sesion y contexto activo.
```

## Responsive y dispositivos

Enfoque:

- desktop first para operacion SaaS B2B;
- tablet razonablemente soportado;
- mobile minimo para consulta, alertas, reportes y acciones simples.

Reglas:

- sidebar colapsable;
- drawer en mobile;
- tablas adaptadas;
- dashboards simplificados;
- tabs con scroll o selector compacto;
- panel derecho como drawer;
- acciones peligrosas visibles y no ambiguas;
- formularios complejos preferentemente desktop;
- no bloquear consulta mobile de alertas y reportes.

## Recomendaciones visuales iniciales

Sin fijar branding final:

- estetica premium B2B;
- contraste alto;
- densidad de informacion equilibrada;
- jerarquia tipografica clara;
- estados consistentes;
- iconografia sobria;
- cards limpias;
- badges con semantica estable;
- espacios suficientes para lectura;
- foco visible para accesibilidad.

Evitar:

- aspecto de landing comercial dentro de consola;
- panel administrativo generico saturado;
- exceso de cards sin jerarquia;
- color como unico indicador;
- animaciones que interfieran con operacion;
- detalles tecnicos irrelevantes para cliente.

## Implicancias para Astro

Astro debe ser la base de:

- rutas;
- layouts;
- paginas base;
- carga inicial;
- separacion publica/privada;
- entrega eficiente del shell.

Layouts conceptuales:

| Layout | Responsabilidad |
| --- | --- |
| `PublicMarketingLayout` | Sitio comercial `team360.live` |
| `ConsoleAuthLayout` | Login, recuperacion y seleccion inicial |
| `ConsoleAppLayout` | Shell autenticado completo |
| `ConsoleMinimalLayout` | Vistas enfocadas, errores o acciones puntuales |

Rutas conceptuales, sin implementarlas:

```text
/login
/select-workspace
/w/[workspaceId]
/w/[workspaceId]/services
/w/[workspaceId]/services/[serviceId]
/w/[workspaceId]/reports
/w/[workspaceId]/settings
```

Astro puede cargar contexto inicial y pasar props a componentes Svelte. La forma definitiva depende del contrato backend y del modelo de autenticacion.

## Implicancias para Svelte 5 con Runes

Svelte debe concentrar componentes interactivos:

- sidebar;
- topbar;
- switchers;
- notificaciones;
- command palette;
- filtros;
- tablas;
- tabs;
- dashboards;
- paneles laterales;
- formularios;
- confirmaciones;
- estados dinamicos.

Estado sugerido:

```text
currentUser
activeOrganization
activeWorkspace
effectivePermissions
enabledModules
contractedServices
navigationItems
notifications
serviceContext
uiPreferences
authorizedTree
```

Reglas:

- usar Runes para estado derivado;
- derivar navegacion desde contexto;
- separar componentes puros de componentes con datos;
- preparar tabs dinamicas;
- manejar loading, error y empty states;
- descartar respuestas obsoletas tras cambiar contexto;
- no autorizar en frontend.

## Configuracion declarativa de navegacion

Estructura conceptual:

```ts
const navigationRegistry = [
  {
    id: "services",
    label: "Servicios",
    module: "services",
    requiredPermissions: ["services.read"],
    contexts: ["team360", "partner", "client"],
    children: [],
  },
];
```

Es una idea conceptual, no una implementacion obligatoria.

La estructura final puede incluir:

```text
id
label
icon
route
group
module
requiredPermissions
contexts
workspaceRequirement
visibilityMode
badgeSource
children
```

## Bootstrap de contexto desde backend

El backend debe entregar algo equivalente a:

```text
current_user
active_membership
accessible_organizations
accessible_workspaces
effective_permissions
enabled_modules
contracted_services
authorized_tree
notification_summary
feature_flags
ui_hints
```

`ui_hints` es opcional y nunca reemplaza autorizacion.

El frontend puede derivar la interfaz, pero no autorizar por si mismo. Cada request privada debe volver a validar identidad, workspace, permisos y alcance.

## Reglas UX iniciales

1. Mostrar siempre contexto activo.
2. No usar una navegacion universal.
3. No duplicar consolas por rol.
4. No exponer workers a clientes salvo necesidad.
5. No hardcodear `Mamá Mía 360`.
6. No mezclar lenguaje de landing con consola.
7. Mostrar resultados antes que procesos tecnicos para clientes.
8. Mostrar a partners su red, no la red global.
9. Permitir profundidad tecnica global a Team360 segun permisos.
10. Exigir permiso backend para toda accion sensible.
11. Orientar con empty states.
12. Hacer errores accionables y seguros.
13. Mantener switchers claros.
14. Evitar revelar datos ajenos en badges, busquedas o notificaciones.

## Riesgos a evitar

- construir un admin panel generico;
- crear tres consolas separadas;
- hardcodear navegacion por rol;
- disenar sin contexto activo;
- ocultar opciones solo en frontend;
- exponer logs o credenciales a clientes;
- convertir la primera version en una mega-consola;
- disenar estetica antes que patrones UX;
- mezclar dashboards, servicios y workers sin jerarquia;
- ignorar mobile minimo para alertas y reportes;
- renderizar datos antes de validar contexto;
- reutilizar estado del workspace anterior tras un cambio.

## Proximos pasos recomendados

1. Definir design tokens iniciales.
2. Definir primitives y componentes base.
3. Crear wireframes de baja fidelidad del App Shell.
4. Definir navegacion declarativa inicial.
5. Definir contrato de bootstrap backend.
6. Priorizar MVP de consola por rol y recorrido.
7. Definir primeras rutas conceptuales para validacion.
8. Definir primer set de servicios demo.
9. Validar switchers y estados con el caso configurable de partner.

## Restricciones

- No implementar codigo en esta etapa.
- No crear componentes.
- No modificar rutas reales.
- No tocar DB.
- No crear migraciones.
- No cambiar configuracion de build.
- No duplicar la documentacion previa.
