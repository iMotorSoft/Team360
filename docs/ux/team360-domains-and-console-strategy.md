# Team360: separacion de dominios y estrategia de consola

Estado de decision: `aprobado / base estrategica`

Fecha: `2026-05-31`

Audiencia: producto, diseno, frontend, backend y direccion comercial.

Referencias relacionadas:

- ADR resumido: `../adr/ADR-001-team360-domain-separation-and-console.md`
- Arquitectura viva: `../../lat.md/console-multi-organization.md`
- Modelo multi-paquete / multi-worker: `../../lat.md/multi-package-workers.md`

## Resumen ejecutivo

Team360 se divide en dos dominios funcionales con objetivos, lenguaje y experiencia diferentes:

| Dominio | Funcion | Audiencia principal |
| --- | --- | --- |
| `team360.live` | Sitio publico comercial e institucional | Prospectos, empresas, dueños, gerentes y potenciales distribuidores |
| `console.team360.live` | Plataforma privada operativa | Equipo Team360, distribuidores regionales y clientes finales |

La consola se denomina conceptualmente **Team360 Console**. No debe disenarse como un panel aislado para un cliente, sino como una plataforma multi-organizacion capaz de representar toda la red comercial y operativa.

`Mamá Mía 360` sera la primera instancia real de `Partner / Distribuidor Regional` para Israel. No es una excepcion del producto: inaugura un modelo reutilizable para futuros distribuidores por region, pais o nicho.

## Decision de dominios

### `team360.live`

`team360.live` es la home publica comercial. Su trabajo es explicar valor, generar confianza y facilitar conversion.

Debe incluir progresivamente:

- propuesta de valor;
- problemas que Team360 resuelve;
- casos de uso;
- paquetes iniciales;
- diagnostico de automatizacion;
- modelo para distribuidores;
- contacto comercial;
- contenido institucional y evidencia de resultados.

No debe parecer una herramienta tecnica. El sitio debe hablar de resultados, operacion, control, ahorro de tiempo y capacidad de crecimiento. Conceptos como workers, scopes, ejecuciones internas o configuraciones de credenciales no deben dominar la experiencia publica.

### `console.team360.live`

`console.team360.live` es Team360 Console: la plataforma privada para administrar la red y observar resultados.

Debe permitir progresivamente:

- administrar organizaciones y workspaces;
- administrar distribuidores, clientes y equipos;
- contratar y configurar paquetes y servicios;
- operar workers y automatizaciones;
- observar ejecuciones, alertas y tareas;
- consultar dashboards y reportes;
- controlar roles y permisos;
- gestionar integraciones, soporte y facturacion segun alcance.

La consola debe funcionar como centro de operaciones. Su estructura, navegacion y permisos deben adaptarse al contexto del usuario autenticado.

## Justificacion estrategica

Separar sitio y consola evita mezclar dos problemas diferentes:

- La home debe reducir friccion comercial y presentar una propuesta clara.
- La consola debe soportar operacion diaria, datos privados, autorizacion y trazabilidad.

La separacion tambien permite evolucionar despliegues, performance, analitica, seguridad y ciclos de cambio de forma independiente. Puede existir un sistema visual compartido, pero no una unica experiencia indiferenciada.

## Modelo multi-organizacion

### Principio

Team360 es la organizacion raiz de la red. Cada distribuidor y cada cliente se representa como una organizacion con alcance propio. Los workspaces son contextos operativos pertenecientes a una organizacion.

```text
Team360
|-- Cliente directo A
|-- Cliente directo B
`-- Distribuidor Mamá Mía 360
    |-- Cliente MM360 A
    |-- Cliente MM360 B
    `-- Cliente MM360 C
```

### Organization y Workspace

`Organization` y `Workspace` no son sinonimos:

| Concepto | Responsabilidad |
| --- | --- |
| `Organization` | Entidad comercial, contractual y de aislamiento dentro de la red |
| `Workspace` | Contexto operativo donde viven servicios, configuraciones, ejecuciones, resultados y accesos concretos |

Una organizacion puede tener uno o varios workspaces. Un usuario pertenece a una organizacion y puede acceder a uno o varios workspaces autorizados.

### Tipos iniciales de organizacion

| Tipo | Parent permitido | Alcance |
| --- | --- | --- |
| `team360_root` | Ninguno | Administra toda la red |
| `partner` | `team360_root` | Administra su propia organizacion y sus clientes |
| `direct_client` | `team360_root` | Accede a sus propios workspaces y resultados |
| `partner_client` | `partner` | Accede a sus propios workspaces y resultados |

La jerarquia inicial es deliberadamente simple. Cualquier profundidad adicional debe justificarse con un caso real y una politica de permisos clara.

## Caso Mamá Mía 360

`Mamá Mía 360` se modela como:

```text
Organization
  type: partner
  region: Israel
  parent: Team360
```

Puede simultaneamente:

- contratar servicios para su propia operacion;
- distribuir servicios Team360 en Israel;
- administrar clientes propios;
- asignar acceso a su equipo;
- consultar resultados agregados de su red permitida;
- acceder a dashboards y reportes de sus clientes segun permisos.

No puede:

- ver clientes directos de Team360;
- ver otros distribuidores;
- ver clientes de otros distribuidores;
- acceder a workspaces fuera de su subarbol autorizado;
- recibir permisos globales por el solo hecho de ser partner.

La region `Israel` es dato configurable, no logica hardcodeada.

## Entidades principales

| Entidad | Proposito |
| --- | --- |
| `Organization` | Representa Team360, un distribuidor o un cliente dentro de la red |
| `Workspace` | Delimita una operacion concreta y su aislamiento de datos |
| `User` | Identidad autenticada de una persona |
| `Role` | Agrupacion de responsabilidades asignables |
| `Permission` | Capacidad atomica autorizable |
| `Partner / Distributor` | Organizacion hija que puede administrar clientes propios |
| `Direct Client` | Cliente contratado directamente por Team360 |
| `Partner Client` | Cliente gestionado por un distribuidor |
| `Package` | Oferta comercial agrupada |
| `Service` | Prestacion contratada que el cliente reconoce y consulta |
| `Worker` | Pieza tecnica que ejecuta o asiste una automatizacion |
| `Run / Execution` | Ejecucion trazable de una tarea o automatizacion |
| `Dashboard` | Vista interactiva de resultados e indicadores |
| `Report` | Salida consultable o exportable con periodo y alcance definidos |
| `Alert` | Evento que requiere visibilidad o accion |
| `Task` | Unidad operativa manual, automatizada o asistida |
| `Integration` | Conexion controlada con sistemas externos |

## Relaciones principales

```text
Organization
  -> child Organization
  -> Workspace
      -> User access
      -> Service
          -> Package reference
          -> Worker configuration
          -> Run / Execution
          -> Dashboard
          -> Report
          -> Alert
          -> Task
          -> Integration
```

Reglas:

- Team360 es la organizacion raiz.
- Un partner depende de Team360.
- Un cliente directo depende de Team360.
- Un cliente de partner depende de ese partner.
- Un usuario pertenece a una organizacion y recibe acceso explicito a workspaces.
- La visibilidad heredada solo baja por el subarbol permitido; nunca se extiende lateralmente.
- Cada recurso operativo debe resolverse dentro de un contexto de organizacion y workspace.

## Roles esperados

Los nombres finales pueden ajustarse, pero el modelo debe soportar al menos:

| Rol conceptual | Alcance esperado |
| --- | --- |
| `team360_platform_admin` | Red completa, configuracion global y soporte controlado |
| `team360_operator` | Operacion autorizada sobre clientes y servicios asignados |
| `partner_admin` | Organizacion partner y clientes propios |
| `partner_operator` | Operacion delegada dentro de la red del partner |
| `partner_analyst` | Lectura de resultados y reportes permitidos |
| `client_admin` | Workspaces de su organizacion, equipo y servicios contratados |
| `client_operator` | Tareas, alertas y automatizaciones permitidas |
| `client_viewer` | Lectura de dashboards y reportes |
| `support_scoped` | Acceso temporal y auditable a organizaciones autorizadas |

Los roles no reemplazan permisos atomicos. El backend debe aplicar permisos y alcance de datos; ocultar una opcion en UI no constituye autorizacion.

## Paquete, servicio, worker y dashboard

| Concepto | Pregunta que responde | Visibilidad |
| --- | --- | --- |
| `Package` | Que oferta comercial se vende o habilita | Comercial y administrativa |
| `Service` | Que prestacion entiende el cliente que contrato | Cliente, partner y operacion |
| `Worker` | Que componente tecnico ejecuta una capacidad | Principalmente interna |
| `Dashboard` | Que resultados puede observar el usuario | Cliente, partner y operacion segun scope |

Ejemplo:

```text
Package: Operacion Marketplace
  -> Service: Gestion de preguntas de Mercado Libre
      -> Worker: meli_browser_worker
      -> Runs: ejecuciones trazables
      -> Dashboard: volumen, tiempos, estado y resultados
```

Los clientes no interactuan directamente con workers. Esta regla extiende el modelo documentado en `lat.md/multi-package-workers.md`.

## Navegacion sugerida

La navegacion final debe derivarse del rol, permisos y contexto seleccionado. Estas listas definen la arquitectura de informacion inicial, no menus rigidos.

### Team360 Admin

- Inicio
- Organizaciones
- Distribuidores
- Clientes
- Paquetes
- Servicios
- Workers
- Dashboards
- Ejecuciones
- Alertas
- Usuarios
- Facturacion
- Soporte
- Configuracion

### Distribuidor

- Inicio
- Mis clientes
- Mis servicios
- Leads
- Resultados
- Reportes
- Equipo
- Paquetes disponibles
- Soporte
- Configuracion

### Cliente final

- Inicio
- Servicios contratados
- Resultados
- Reportes
- Automatizaciones
- Archivos
- Alertas
- Equipo
- Soporte

## Implicancias para UX/UI

### Dos experiencias, una marca

- La home publica prioriza claridad comercial, confianza y conversion.
- Team360 Console prioriza contexto, estado operativo, acciones y trazabilidad.
- Ambas superficies pueden compartir identidad visual, pero no deben compartir la misma jerarquia de informacion.

### Contexto visible

La consola debe mostrar siempre el contexto activo cuando un usuario pueda operar mas de una organizacion o workspace:

- organizacion seleccionada;
- workspace seleccionado;
- rol o alcance relevante;
- region cuando aporte contexto;
- filtros de periodo para resultados.

Los cambios de contexto deben ser explicitos. Una persona no debe ejecutar una accion creyendo estar dentro de otro cliente.

### Lenguaje por audiencia

- Cliente final: servicios, resultados, alertas, automatizaciones y reportes.
- Distribuidor: red propia, clientes, leads, resultados agregados y equipo.
- Equipo Team360: organizaciones, permisos, workers, ejecuciones, integraciones y soporte.

Los detalles tecnicos deben aparecer solo cuando el rol y la tarea los requieren.

### Navegacion progresiva

- No exponer menus vacios o no autorizados.
- Priorizar el resumen operativo en Inicio.
- Permitir profundizar desde resultado visible hacia servicio, ejecucion y evidencia.
- Mantener workers y configuracion avanzada fuera de la experiencia normal del cliente.
- Disenar estados vacios, errores, carga, permisos insuficientes y soporte como parte del flujo base.

## Implicancias para frontend: Astro + Svelte 5 con Runes

### Separacion de superficies

- `team360.live` debe usar Astro como base para rutas publicas, layouts, contenido, SEO y performance.
- `console.team360.live` debe usar Astro para rutas y layouts de aplicacion, con componentes Svelte 5 para interactividad operativa.
- La consola puede evolucionar como despliegue independiente aunque comparta repositorio, tokens visuales y componentes base.
- No debe asumirse que la home publica y la consola comparten navegacion, sesion o ciclo de release.

### Componentes interactivos

Svelte 5 con Runes debe concentrar:

- selector de organizacion y workspace;
- estado de sesion visible;
- tablas y filtros operativos;
- dashboards;
- alertas y tareas;
- formularios de configuracion;
- actualizaciones de estado y flujos asistidos.

Astro debe mantener la estructura de pagina y cargar interactividad donde aporte valor. No es necesario convertir toda la consola en una SPA monolitica desde el inicio.

### Estado de consola

El estado cliente debe distinguir:

```text
session
activeOrganization
activeWorkspace
grantedPermissions
availableContexts
featureAvailability
```

Las Runes pueden gestionar estado local y compartido de UI, pero el backend sigue siendo la fuente de verdad para autorizacion, membresias y resultados.

### Componentes compartidos iniciales

Conviene preparar, cuando comience la implementacion:

- layout publico;
- layout autenticado de consola;
- selector de contexto;
- navegacion por capacidades;
- tablas operativas;
- tarjetas de resultado;
- estados vacios;
- alertas;
- panel de soporte;
- primitives visuales compartidos.

## Implicancias para backend, permisos y multi-tenant

### Brecha respecto del schema actual

Las migraciones actuales `001` y `002` ya modelan `core_workspaces`, `core_users`, RBAC, paquetes y workers. Sin embargo, todavia no modelan completamente:

- `organizations`;
- jerarquia padre-hijo;
- tipo de organizacion;
- region configurable;
- membresias de usuario por organizacion;
- acceso de un usuario a multiples workspaces;
- servicios como entidad visible para cliente;
- alcance delegado para partners.

Esta decision no modifica migraciones existentes. Antes de implementar Team360 Console debe disenarse una migracion nueva y auditable.

### Contexto de autorizacion

Cada request privada debe resolver como minimo:

```text
authenticated_user_id
organization_id
workspace_id
granted_permissions
allowed_organization_scope
```

El backend debe verificar:

- autenticacion valida;
- membresia de organizacion;
- acceso al workspace;
- permiso atomico requerido;
- pertenencia del recurso al workspace;
- alcance jerarquico permitido;
- auditoria de cambios sensibles.

### Aislamiento

- Team360 puede administrar la red completa.
- Un partner solo puede operar su organizacion y descendientes permitidos.
- Un cliente solo puede operar sus propios workspaces.
- Ningun filtro del frontend reemplaza controles de backend.
- Consultas, repositories y eventos deben conservar `organization_id` y `workspace_id` cuando corresponda.
- RLS de PostgreSQL puede evaluarse como defensa adicional, sin reemplazar la autorizacion de aplicacion.

## Reglas iniciales de diseno

1. Llamar a la plataforma privada **Team360 Console**.
2. Mantener separados el sitio comercial y la operacion privada.
3. Disenar toda vista privada con contexto de organizacion y workspace.
4. Modelar partners como organizaciones configurables, nunca como casos especiales.
5. Mostrar al cliente servicios y resultados antes que componentes tecnicos.
6. Mantener workers como detalle interno salvo necesidades operativas autorizadas.
7. Derivar navegacion de permisos y capacidades.
8. Exigir confirmacion y auditoria para acciones sensibles.
9. Disenar mobile responsive para consulta, sin asumir que toda operacion compleja se realizara desde movil.
10. Preparar internacionalizacion, timezone y region sin hardcodear Israel ni un idioma unico.

## Riesgos a evitar

- Disenar la consola como panel exclusivo de un solo cliente.
- Usar `workspace` como sustituto permanente de organizacion comercial.
- Hardcodear `Mamá Mía 360`, Israel o una jerarquia especifica.
- Permitir visibilidad lateral entre distribuidores o clientes.
- Exponer workers y jerga tecnica en la home publica.
- Crear una navegacion unica con opciones ocultas solo por CSS.
- Confiar en filtros de UI para aislamiento multi-tenant.
- Duplicar logica de autorizacion en componentes sin contrato backend.
- Disenar dashboards sin trazabilidad hacia ejecuciones y evidencia.
- Mezclar el ritmo de cambios comerciales de la home con cambios operativos de consola.

## Proximos pasos recomendados

1. Disenar el modelo de datos objetivo para organizaciones, jerarquia, membresias, accesos multi-workspace y servicios.
2. Crear una matriz inicial de roles, permisos y scopes por tipo de organizacion.
3. Definir sitemap y wireframes de baja fidelidad para `team360.live`.
4. Definir sitemap y wireframes de Team360 Console para Team360 Admin, partner y cliente final.
5. Disenar el selector de organizacion/workspace y los estados de cambio de contexto.
6. Definir el contrato backend de contexto tenant y autorizacion antes de implementar pantallas privadas.
7. Disenar el primer onboarding real de `Mamá Mía 360` como instancia configurable de partner.
8. Separar backlog de home publica, consola privada y evolucion de schema.
