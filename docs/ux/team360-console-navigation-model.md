# Team360 Console: modelo de navegacion contextual por rol y organizacion

Estado de decision: `aprobado / base estrategica para diseno`

Fecha: `2026-05-31`

Audiencia: producto, UX/UI, frontend, backend y direccion comercial.

Referencias relacionadas:

- Estrategia de dominios: `team360-domains-and-console-strategy.md`
- ADR resumido: `../adr/ADR-002-team360-console-navigation-by-role.md`
- Arquitectura viva: `../../lat.md/console-multi-organization.md`
- Modelo multi-paquete / multi-worker: `../../lat.md/multi-package-workers.md`

## Resumen ejecutivo

Team360 Console no tendra una navegacion fija para todos los usuarios. La navegacion se deriva del contexto autenticado y operativo:

```text
organization_type
role
permissions
active_organization
active_workspace
contracted_services
available_modules
allowed_organization_scope
```

El rol aporta una base comprensible para negocio y UX, pero no es la unica fuente de decision. Los permisos efectivos, el workspace activo y los servicios contratados determinan que modulos, acciones y datos puede consultar cada usuario.

La consola debe mantener un unico App Shell adaptable. No conviene crear una aplicacion separada para Team360, otra para distribuidores y otra para clientes. La diferenciacion debe resolverse mediante contexto, modulos y permisos.

## Alcance

Este documento define:

- principio general de navegacion;
- contexto activo obligatorio;
- App Shell y layouts conceptuales;
- navegacion por tipo de organizacion y rol;
- navegacion interna de servicios;
- estados visibles de items;
- wireframes textuales iniciales;
- implicancias para Astro, Svelte 5 con Runes y backend;
- reglas UX y riesgos.

Queda fuera de alcance:

- implementar pantallas;
- crear componentes;
- modificar rutas reales;
- definir estilos visuales finales;
- modificar DB;
- crear navegacion funcional;
- fijar pricing o branding definitivo.

## Principio general de navegacion

### Navegacion contextual

La navegacion visible se calcula a partir de:

| Dimension | Pregunta que responde |
| --- | --- |
| `organization_type` | Que clase de organizacion esta operando el usuario |
| `role` | Que responsabilidad general tiene dentro del contexto |
| `permissions` | Que capacidades atomicas puede ejercer realmente |
| `active_organization` | Sobre que organizacion esta consultando u operando |
| `active_workspace` | En que contexto operativo concreto trabaja |
| `contracted_services` | Que prestaciones existen y deben ser visibles |
| `available_modules` | Que partes de la consola estan habilitadas |
| `allowed_organization_scope` | Que subarbol puede consultar o administrar |

Regla:

```text
visible_navigation =
  declared_modules
  filtered by organization_type
  filtered by available_modules
  filtered by effective_permissions
  adapted to active_workspace
  enriched by contracted_services and status
```

### Roles como perfiles iniciales

Los roles simplifican onboarding y administracion. No deben convertirse en condicionales rigidos dispersos por el frontend.

Ejemplo:

```text
partner_admin
  -> perfil inicial de permisos
  -> ajustado por scope delegado
  -> ajustado por workspace activo
  -> ajustado por modulos habilitados
```

Dos usuarios con el mismo rol pueden ver diferencias legitimas si administran workspaces distintos o si uno tiene un permiso delegado adicional.

## Tipos de organizacion

| Tipo conceptual | Codigo sugerido | Alcance base |
| --- | --- | --- |
| Team360 Owner / Root Organization | `team360_root` | Red completa |
| Partner / Distributor | `partner` | Organizacion propia y descendientes autorizados |
| Direct Client | `direct_client` | Workspaces propios |
| Partner Client | `partner_client` | Workspaces propios bajo un partner |

`Mamá Mía 360` es un ejemplo concreto de `partner` para Israel. La navegacion no debe contener condiciones especiales por nombre, pais o primer distribuidor.

## Roles iniciales

### Team360

| Rol | Proposito |
| --- | --- |
| Super Admin Team360 | Administracion global restringida, configuracion critica y gobierno de red |
| Admin Team360 | Administracion operativa de organizaciones, servicios y usuarios |
| Operator Team360 | Operacion diaria de servicios, workers asignados, ejecuciones y alertas |
| Support Team360 | Seguimiento de solicitudes, clientes asignados y evidencias |
| Finance / Billing Team360 | Facturacion, suscripciones, estados comerciales y reportes habilitados |
| Viewer Team360 | Consulta autorizada sin cambios operativos |

### Partner / Distribuidor

| Rol | Proposito |
| --- | --- |
| Admin Distribuidor | Gestion de organizacion partner, equipo, clientes propios y servicios permitidos |
| Comercial Distribuidor | Leads, oportunidades, paquetes disponibles y seguimiento comercial |
| Operador Distribuidor | Operacion delegada de servicios y resultados de su red |
| Soporte Distribuidor | Solicitudes, clientes asignados, evidencias y escalamiento |
| Viewer Distribuidor | Consulta de resultados y reportes autorizados |

### Cliente final

Aplica tanto a `direct_client` como a `partner_client`.

| Rol | Proposito |
| --- | --- |
| Admin Cliente | Gestion de equipo, servicios contratados y configuracion habilitada |
| Operador Cliente | Seguimiento de automatizaciones, tareas y alertas permitidas |
| Viewer Cliente | Lectura de resultados y reportes |
| Aprobador / Responsable de negocio | Revision y aprobacion de acciones sensibles o resultados que requieren HITL |

## Contexto activo

### Regla

El usuario nunca debe quedar sin contexto operativo visible. La consola debe indicar:

- identidad del usuario;
- rol efectivo;
- organizacion activa;
- tipo de organizacion activa;
- workspace activo;
- organizacion propietaria del workspace;
- subarbol autorizado;
- si la vista corresponde a datos propios o delegados;
- periodo activo cuando la vista presenta resultados.

Ejemplo conceptual:

```text
Estoy viendo como: Admin Distribuidor
Organizacion activa: Mamá Mía 360
Workspace activo: Mamá Mía 360
Subarbol visible: clientes propios de Mamá Mía 360
Modo de acceso: organizacion propia
```

Ejemplo al ingresar a un cliente delegado:

```text
Estoy viendo como: Admin Distribuidor
Organizacion activa: Cliente MM360 A
Workspace activo: Operacion principal
Organizacion propietaria: Cliente MM360 A
Subarbol autorizado por: Mamá Mía 360
Modo de acceso: cliente gestionado
```

### Cambios de contexto

- El cambio de organizacion debe ser explicito.
- El cambio de workspace debe ser explicito.
- La consola debe restaurar un contexto valido al volver a iniciar sesion.
- Si el contexto guardado dejo de ser valido, debe solicitar seleccion antes de mostrar datos.
- Las acciones sensibles deben volver a mostrar organizacion y workspace antes de confirmar.
- El selector no debe listar organizaciones fuera del subarbol autorizado.

### Contexto propio y contexto delegado

La UI debe diferenciar:

| Modo | Ejemplo | Tratamiento UX |
| --- | --- | --- |
| Propio | Partner operando su organizacion | Contexto normal |
| Cliente directo | Team360 operando un cliente directo | Mostrar cliente y origen Team360 |
| Cliente de partner | Partner operando un cliente propio | Mostrar cliente y partner responsable |
| Soporte delegado | Soporte operando un cliente asignado | Mostrar acceso delegado y alcance |
| Solo lectura | Viewer consultando resultados | Indicar restricciones de edicion |

## Layout base recomendado

### App Shell

Team360 Console debe tener un App Shell comun con variantes contextuales:

```text
+-----------------------------------------------------------------------+
| Topbar: contexto activo | busqueda | notificaciones | cuenta          |
+----------------------+------------------------------------------------+
| Sidebar contextual   | Breadcrumbs                                    |
|                      +------------------------------------------------+
| navegacion global    | Main content area                              |
| por capacidades      |                                                |
|                      |                                                |
|                      |                                   Right panel  |
|                      |                                   opcional      |
+----------------------+------------------------------------------------+
```

### Elementos del shell

| Elemento | Responsabilidad |
| --- | --- |
| App Shell | Mantiene estructura estable de consola |
| Sidebar contextual | Expone modulos globales permitidos |
| Topbar | Muestra contexto activo y acciones globales |
| Organization switcher | Permite cambiar organizacion cuando el scope lo autoriza |
| Workspace switcher | Permite cambiar contexto operativo |
| Breadcrumbs | Explican profundidad y origen de la vista |
| Main content area | Presenta la vista principal |
| Right panel opcional | Actividad, ayuda contextual, detalle o soporte |
| Notification center | Centraliza alertas, pendientes y eventos relevantes |
| User/account menu | Cuenta, preferencias, sesion y ayuda |

### Organization switcher

Debe aparecer solo cuando el usuario tenga acceso a mas de una organizacion o necesite recorrer un subarbol delegado.

Debe permitir:

- buscar por nombre;
- distinguir Team360, partner, cliente directo y cliente de partner;
- mostrar relacion jerarquica;
- indicar contexto reciente;
- impedir seleccionar organizaciones fuera del alcance.

### Workspace switcher

Debe aparecer cuando la organizacion activa tenga mas de un workspace o cuando cambiar de operacion sea relevante.

Debe mostrar:

- nombre del workspace;
- organizacion propietaria;
- estado;
- region o timezone cuando aporte contexto;
- servicios activos resumidos;
- indicador de alertas si corresponde.

## Estados de navegacion y permisos

Un item de navegacion puede estar:

| Estado | Uso |
| --- | --- |
| Visible y habilitado | El usuario puede ingresar y operar segun permisos |
| Visible en solo lectura | El usuario puede consultar, pero no modificar |
| Visible deshabilitado | El modulo existe, pero requiere habilitacion, servicio o accion previa |
| Oculto | El usuario no debe descubrir el modulo o no tiene alcance |
| Con badge | Hay alertas, tareas, ejecuciones fallidas o pendientes |
| Con estado | Conviene indicar `beta`, `configuracion pendiente`, `requiere soporte` o similar |

Ejemplos:

- Viewer Cliente puede ver reportes, pero no modificar integraciones.
- Admin Distribuidor puede crear usuarios de su equipo, pero no cambiar workers internos de Team360.
- Operator Team360 puede ver ejecuciones tecnicas, pero no necesariamente facturacion.
- Aprobador Cliente puede ver tareas de aprobacion y evidencia, pero no configurar el servicio.

Regla: ocultar o deshabilitar en frontend mejora UX, pero nunca reemplaza validacion backend.

## Navegacion global para Team360 Admin

Aplica a Super Admin y Admin Team360 con diferencias de permisos efectivos.

| Seccion | Objetivo |
| --- | --- |
| Inicio | Resumen de red, servicios, alertas y actividad relevante |
| Organizaciones | Arbol general de organizaciones y estado |
| Distribuidores | Gestion de partners, regiones, equipos y red autorizada |
| Clientes | Gestion de clientes directos y acceso controlado a clientes de partners |
| Workspaces | Contextos operativos, propietarios, estados y accesos |
| Paquetes | Catalogo comercial y composicion habilitada |
| Servicios | Prestaciones contratadas y su estado operativo |
| Workers | Capacidades tecnicas, asignaciones y salud operativa |
| Ejecuciones | Runs, estados, errores, reintentos y evidencia |
| Dashboards | Vistas de indicadores disponibles |
| Reportes | Salidas consultables o exportables |
| Alertas | Incidentes, advertencias y pendientes |
| Tareas | Trabajo manual, asistido o pendiente de aprobacion |
| Integraciones | Conexiones controladas con sistemas externos |
| Usuarios | Identidades y membresias |
| Roles y permisos | Perfiles, permisos efectivos y delegaciones |
| Facturacion | Suscripciones, cargos, estados y alcance comercial |
| Soporte | Solicitudes, seguimiento y escalamiento |
| Auditoria | Eventos sensibles, cambios y trazabilidad |
| Configuracion | Parametros globales permitidos |

### Diferencia entre Super Admin y Admin

- Super Admin Team360 accede a configuracion critica y gobierno global.
- Admin Team360 administra la red dentro de permisos delegados.
- La existencia de Super Admin no habilita uso diario indiscriminado.
- Las acciones criticas deben quedar auditadas y, cuando corresponda, exigir confirmacion adicional.

## Navegacion global para Partner / Distribuidor

| Seccion | Objetivo |
| --- | --- |
| Inicio | Estado de la organizacion partner y resumen de su red |
| Mis clientes | Clientes propios, workspaces y estado |
| Leads | Prospectos y seguimiento comercial si el modulo esta habilitado |
| Mis servicios | Servicios contratados por el partner para su propia operacion |
| Servicios de mis clientes | Servicios activos dentro del subarbol autorizado |
| Resultados | Indicadores propios y agregados permitidos |
| Reportes | Reportes propios o de clientes segun scope |
| Paquetes disponibles | Oferta comercial habilitada para distribuir |
| Equipo | Usuarios, roles y accesos de la organizacion partner |
| Soporte | Solicitudes propias y escalamiento permitido |
| Configuracion | Preferencias y configuracion autorizada |
| Marca / Branding | Personalizacion habilitada si el modelo comercial lo contempla |

### Puede ver

- su organizacion;
- workspaces propios;
- equipo propio;
- clientes descendientes autorizados;
- servicios contratados propios;
- servicios de sus clientes cuando el scope lo permite;
- resultados y reportes agregados permitidos;
- paquetes habilitados para su canal.

### No puede ver

- otros partners;
- clientes directos de Team360;
- clientes de otros partners;
- configuracion global de plataforma;
- workers internos salvo vistas operativas expresamente delegadas;
- credenciales, logs o auditoria fuera de su scope.

## Navegacion global para Cliente Final

Aplica a clientes directos y clientes de partner. El origen contractual puede cambiar soporte o branding, pero no debe fragmentar innecesariamente la experiencia.

| Seccion | Objetivo |
| --- | --- |
| Inicio | Resumen de servicios, resultados, alertas y pendientes |
| Servicios contratados | Prestaciones activas y estado |
| Resultados | KPIs y salidas comprensibles |
| Reportes | Consulta y descarga autorizada |
| Automatizaciones | Flujos visibles en lenguaje de negocio |
| Archivos | Evidencias, entradas o salidas permitidas |
| Alertas | Situaciones que requieren atencion |
| Tareas | Acciones manuales o aprobaciones pendientes |
| Equipo | Usuarios y accesos autorizados |
| Soporte | Solicitudes y ayuda |
| Configuracion | Preferencias y parametros permitidos |

### Profundidad tecnica

El cliente final no deberia ver workers, credenciales, logs internos ni configuracion de infraestructura salvo que exista un caso explicito y permisos especiales. Debe entender:

- que servicio tiene;
- que esta funcionando;
- que resultado obtuvo;
- que requiere atencion;
- que accion debe realizar.

## Navegacion especializada para Operator Team360

Operator Team360 necesita una vista orientada a trabajo operativo, no una replica reducida del panel administrativo.

| Seccion | Objetivo |
| --- | --- |
| Cola de trabajo | Priorizar trabajo pendiente y bloqueos |
| Ejecuciones | Revisar runs, fallas, reintentos y evidencia |
| Alertas tecnicas | Atender incidentes operativos |
| Workers asignados | Consultar salud y asignaciones bajo su responsabilidad |
| Clientes asignados | Cambiar contexto solo dentro del alcance delegado |
| Servicios activos | Consultar estado de prestaciones operadas |
| Logs resumidos | Diagnosticar sin exponer secretos |
| Tareas pendientes | Resolver acciones manuales o escalar |
| Soporte operativo | Coordinar incidentes y seguimiento |

Un operador no debe recibir automaticamente acceso a facturacion, gobierno global ni administracion completa de usuarios.

## Navegacion especializada para Soporte

Aplica a Support Team360 y Soporte Distribuidor con scopes diferentes.

| Seccion | Objetivo |
| --- | --- |
| Tickets / solicitudes | Gestionar consultas e incidentes |
| Clientes asignados | Acceder solo a contextos autorizados |
| Estado de servicios | Consultar salud visible y afectacion |
| Historial de actividad | Entender cambios y eventos relevantes |
| Escalamiento | Derivar a operacion, administracion o tercero |
| Contactos del cliente | Identificar responsables autorizados |
| Evidencias / archivos | Adjuntar o consultar material relacionado |

Reglas:

- El soporte debe operar con acceso delegado y auditable.
- La vista de soporte debe evitar secretos y configuracion innecesaria.
- La escalacion debe preservar contexto, evidencias y timeline.

## Navegacion por servicio

### Diferencia con navegacion global

La navegacion global responde:

```text
Que puedo hacer dentro de Team360 Console?
```

La navegacion por servicio responde:

```text
Que puedo consultar o configurar dentro de esta prestacion contratada?
```

Ejemplo:

```text
Servicio: Automatizacion Leads Facebook -> Kommo
```

Tabs posibles:

| Tab | Proposito | Visibilidad habitual |
| --- | --- | --- |
| Resumen | Estado, objetivo, KPIs y pendientes | Todos los roles autorizados |
| Configuracion | Parametros permitidos | Admins y operadores autorizados |
| Ejecuciones | Runs relacionados | Team360; partner o cliente con detalle reducido |
| Resultados | Salidas y metricas | Roles autorizados |
| Reportes | Consultas o exportables | Roles autorizados |
| Alertas | Situaciones del servicio | Roles autorizados |
| Archivos | Entradas, salidas y evidencias | Segun scope |
| Historial | Cambios y actividad | Team360; lectura reducida cuando corresponda |
| Soporte | Solicitudes contextualizadas | Todos los roles autorizados |

### Profundidad variable

El mismo servicio puede presentar distinta profundidad:

```text
Cliente final
  -> resumen, resultados, reportes, alertas, archivos, soporte

Partner autorizado
  -> lo anterior + configuracion delegada + ejecuciones resumidas

Team360
  -> lo anterior + workers, logs resumidos, auditoria y controles operativos
```

## Wireframes textuales iniciales

### Dashboard Team360 Admin

```text
[Topbar]
Team360 / Red global | Workspace: Todos o seleccionado | Alertas | Cuenta

[Sidebar]
Inicio
Organizaciones
Distribuidores
Clientes
Servicios
Workers
Ejecuciones
Alertas
...

[Main]
Fila 1: KPIs de red
  organizaciones activas | partners | clientes | servicios activos

Fila 2: Salud operativa
  ejecuciones recientes | fallas | alertas criticas | tareas pendientes

Fila 3: Actividad comercial y soporte
  altas recientes | servicios pendientes de configurar | tickets abiertos

[Right panel opcional]
Actividad reciente y accesos rapidos
```

### Dashboard Distribuidor

```text
[Topbar]
Organizacion: Mamá Mía 360 | Workspace: Mamá Mía 360 | Alertas | Cuenta

[Sidebar]
Inicio
Mis clientes
Leads
Mis servicios
Servicios de mis clientes
Resultados
Reportes
Equipo
Soporte

[Main]
Fila 1: Resumen de red propia
  clientes activos | leads | servicios activos | alertas

Fila 2: Resultados agregados permitidos
  KPIs por cliente | tendencias | reportes recientes

Fila 3: Pendientes
  onboarding | tareas | solicitudes de soporte
```

`Mamá Mía 360` es texto de ejemplo. El layout se alimenta del contexto activo.

### Dashboard Cliente Final

```text
[Topbar]
Organizacion: Cliente A | Workspace: Operacion principal | Alertas | Cuenta

[Sidebar]
Inicio
Servicios contratados
Resultados
Reportes
Automatizaciones
Archivos
Alertas
Tareas
Soporte

[Main]
Fila 1: Resumen comprensible
  servicios activos | resultados del periodo | alertas | tareas

Fila 2: Servicios
  tarjetas con estado, ultimo resultado y proxima accion

Fila 3: Reportes recientes y actividad relevante
```

### Vista detalle de servicio

```text
[Breadcrumb]
Servicios / Automatizacion Leads Facebook -> Kommo

[Header]
Nombre | estado | workspace | periodo | acciones permitidas

[Tabs derivadas por permisos]
Resumen | Configuracion | Ejecuciones | Resultados | Reportes |
Alertas | Archivos | Historial | Soporte

[Main]
KPIs del servicio | timeline | pendientes | evidencia reciente

[Right panel opcional]
Ayuda contextual | contacto de soporte | actividad
```

### Vista detalle de worker

Solo Team360 o permisos tecnicos expresos.

```text
[Breadcrumb]
Workers / meli_browser_worker

[Header]
Worker | tipo | estado | modo | asignaciones

[Tabs]
Resumen | Asignaciones | Ejecuciones | Salud | Configuracion permitida |
Logs resumidos | Historial

[Main]
Capacidades | servicios relacionados | alertas | ultimas ejecuciones

[Restriccion]
No mostrar secretos. Referencias de credenciales segun permiso.
```

### Selector de Workspace

```text
[Popover]
Buscar workspace...

Recientes
  Mamá Mía 360 / Mamá Mía 360
  Cliente MM360 A / Operacion principal

Mi organizacion
  Mamá Mía 360

Clientes gestionados
  Cliente MM360 A
  Cliente MM360 B

[Cada opcion]
organizacion | workspace | estado | servicios activos | alertas
```

## Implicancias para Astro + Svelte 5 con Runes

### Responsabilidades

Astro debe resolver:

- rutas;
- layouts base;
- paginas iniciales;
- carga inicial del contexto;
- separacion entre superficies publicas y privadas;
- performance y entrega del shell.

Svelte 5 con Runes debe resolver:

- switchers de organizacion y workspace;
- sidebar contextual;
- tabs por servicio;
- filtros;
- notificaciones;
- badges;
- tablas interactivas;
- dashboards;
- acciones y confirmaciones.

### Estado de consola

El frontend debe distinguir al menos:

```text
currentUser
activeOrganization
activeWorkspace
effectiveRole
permissions
availableModules
navigationItems
serviceContext
notifications
allowedOrganizationScope
```

Las Runes pueden coordinar estado de UI y contexto cliente. El backend sigue siendo la fuente de verdad.

### Configuracion declarativa

La navegacion debe definirse como estructuras declarativas evaluables, no como menus repetidos por rol.

Ejemplo conceptual:

```text
navigationItem:
  id
  label
  route
  required_permissions
  allowed_organization_types
  required_modules
  workspace_requirement
  visibility_mode
  badge_source
```

Reglas frontend:

- Derivar navegacion desde permisos efectivos.
- Usar roles como perfiles iniciales, no como unica condicion.
- Evitar duplicar layouts cuando cambia solo la disponibilidad de modulos.
- Resolver tabs de servicio con la misma logica declarativa.
- Mantener separada la definicion visual de la autorizacion real.
- Manejar explicitamente loading, contexto invalido y permiso insuficiente.

## Implicancias para backend

### Bootstrap de consola

El backend debe proveer un contrato inicial para construir la consola sin inferencias inseguras en frontend:

```text
current_user
accessible_organizations
accessible_workspaces
active_context
roles_by_workspace
effective_permissions
available_modules
contracted_services
delegated_scopes
allowed_organization_scope
visibility_restrictions
notification_summary
```

### Autorizacion

Cada request privada debe validar:

```text
authenticated_user_id
active_organization_id
active_workspace_id
resource_organization_id
resource_workspace_id
required_permission
allowed_organization_scope
```

El backend debe:

- resolver membresias;
- validar acceso al workspace;
- calcular permisos efectivos;
- filtrar recursos por scope;
- impedir visibilidad lateral;
- registrar eventos sensibles;
- devolver errores comprensibles para UX;
- evitar exponer secretos en respuestas de consola.

### Contratos de modulos

El backend debe diferenciar:

- permiso para descubrir un modulo;
- permiso para leer;
- permiso para configurar;
- permiso para ejecutar;
- permiso para aprobar;
- permiso para administrar accesos;
- scope de datos visible.

No todos los modulos deben existir para todos los workspaces. La consola debe recibir capacidades habilitadas y estados de configuracion.

## Reglas UX iniciales

1. El usuario nunca debe quedar sin contexto visible.
2. La consola debe mostrar primero servicios, resultados y pendientes.
3. La navegacion debe reducirse segun permisos, modulos y workspace.
4. Team360 puede acceder a profundidad tecnica autorizada.
5. Los clientes finales ven resultados y acciones comprensibles.
6. Los distribuidores ven su red autorizada, no la red global.
7. `Mamá Mía 360` es ejemplo de partner, no excepcion.
8. Toda vista sensible requiere validacion backend.
9. Ocultar una opcion en frontend no constituye autorizacion.
10. Los workers no deben ser protagonistas para clientes salvo necesidad explicita.
11. Los cambios de organizacion o workspace deben ser claros.
12. Las acciones sensibles deben reiterar contexto antes de confirmar.
13. La consola debe soportar estados vacios, carga, error, solo lectura y permiso insuficiente.
14. El MVP debe priorizar los recorridos necesarios, no la totalidad del catalogo administrativo.

## Riesgos a evitar

- Crear una navegacion unica para todos.
- Hardcodear `Mamá Mía 360`, Israel o una jerarquia puntual.
- Mezclar la home comercial con la consola.
- Exponer detalles tecnicos innecesarios al cliente.
- Ocultar por frontend sin validar permisos en backend.
- Confundir paquete, servicio, worker y dashboard.
- Disenar estetica antes de definir contexto y permisos.
- Duplicar layouts completos por rol.
- Inferir autorizacion desde el pathname.
- Cargar datos antes de resolver organizacion y workspace.
- Mostrar badges o estados con informacion fuera del scope permitido.
- Convertir el MVP en una consola administrativa gigante.

## Proximos pasos

1. Definir matriz de modulos, permisos atomicos y roles iniciales.
2. Definir contrato backend de bootstrap de consola.
3. Disenar sitemap MVP por Team360 Admin, Operator Team360, Partner y Cliente Final.
4. Disenar wireframes de baja fidelidad del App Shell y selector de contexto.
5. Definir estados de items, tabs y acciones por servicio.
6. Diseñar modelo de datos futuro para organizaciones, membresias multi-workspace, servicios y scopes delegados.
7. Validar el onboarding de `Mamá Mía 360` como configuracion de partner reutilizable.
8. Separar backlog MVP de extensiones administrativas posteriores.
