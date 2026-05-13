# SAP Business One v10 Desktop Client - Factibilidad de automatizacion asistida

Fecha: 2026-05-13
Proyecto: Team360
Objetivo: documentacion tecnica y comercial interna
Alcance: SAP Business One v10 Desktop Client, sin acceso inicial directo a HANA/SQL, sin marketplace SAP y sin certificacion SAP inicial.

## 1. Resumen ejecutivo

Team360 puede salir rapido al mercado con un servicio privado de automatizacion asistida para empresas que usan SAP Business One, trabajando dentro de la infraestructura del cliente, con su usuario SAP, sus permisos existentes y aprobacion explicita del usuario/empresa.

La oportunidad inicial no es construir un add-on SAP certificado ni una integracion universal. La oportunidad es resolver tareas operativas concretas, repetitivas y de bajo riesgo usando automatizacion asistida sobre una sesion SAP ya autorizada.

### Que se quiere lograr

- Automatizar procesos operativos sobre SAP Business One sin pedir acceso directo inicial a HANA/SQL.
- Reducir friccion comercial evitando, al inicio, certificaciones, add-ons oficiales o procesos de marketplace.
- Usar permisos existentes del usuario SAP del cliente.
- Mantener trazabilidad: logs, screenshots, aprobaciones humanas y resultados auditables.
- Validar valor comercial rapidamente antes de invertir en integraciones mas robustas.

### Que se puede hacer rapido

- Consultas asistidas: stock, clientes, deuda, estado de pedidos.
- Descarga de reportes desde SAP B1 Client.
- Copia controlada de datos desde Excel, WhatsApp o formularios internos hacia SAP.
- Pre-carga o borradores de pedidos simples con aprobacion humana.
- Validaciones repetitivas donde el usuario conserva supervision.

### Que NO conviene prometer

- No prometer que es una solucion SAP certificada.
- No prometer que es un add-on SAP oficial.
- No prometer autonomia 24/7 desde el primer dia.
- No prometer que reemplaza completamente al operador SAP.
- No prometer compatibilidad universal con cualquier pantalla, localizacion, customizacion o add-on del cliente.
- No prometer escritura automatica en procesos criticos sin aprobacion humana.

### Automatizacion privada autorizada vs solucion certificada SAP

La automatizacion privada autorizada opera dentro del entorno del cliente y bajo su aprobacion. Usa una sesion, usuario, permisos e infraestructura definidos por el cliente. Comercialmente se posiciona como servicio privado de automatizacion asistida.

Una solucion certificada SAP, en cambio, apunta a distribucion formal como producto/add-on, con packaging, licenciamiento, validaciones, soporte y procesos de certificacion o aprobacion correspondientes. Ese camino puede ser necesario para escalar como producto SAP formal, pero no es el mejor punto de partida si el objetivo es validar mercado rapido.

Decision inicial recomendada:

```text
Primero servicio privado autorizado.
Despues, si hay traccion, evolucion tecnica y eventualmente camino formal SAP.
```

## 2. Opciones tecnicas evaluadas sin acceso directo a HANA/SQL

### A. Service Layer

#### Que es

SAP Business One Service Layer es una API de extension basada en HTTP/OData para consumir datos y servicios de SAP Business One. Expone objetos de negocio sin requerir que Team360 consulte directamente HANA o SQL.

#### Cuando aplica

Aplica cuando el cliente ya tiene Service Layer instalado, configurado y accesible desde la red donde correra la integracion. En SAP Business One 10.0, Service Layer no queda limitado solamente a HANA: desde 10.0 PL01 tambien soporta instalaciones sobre Microsoft SQL Server.

#### Que necesita el cliente

- SAP Business One v10 con Service Layer disponible.
- Endpoint Service Layer accesible desde el worker o backend autorizado.
- Usuario SAP con permisos suficientes.
- Configuracion de red, TLS/certificados y firewall.
- Aprobacion del cliente para consumir objetos de negocio por API.
- Definicion clara de operaciones permitidas.

#### Ventajas

- Mas robusto que RPA sobre pantalla.
- Menor dependencia de resolucion, idioma, layout o foco de ventana.
- Modelo API claro para consultas y operaciones.
- Mejor base para procesos recurrentes y monitoreables.
- Evita acceso directo a HANA/SQL.
- Permite una arquitectura mas limpia para Team360.

#### Desventajas

- Requiere que Service Layer exista y este operativo.
- Puede requerir intervencion del partner SAP o administrador tecnico.
- Tiene friccion de red, certificados, permisos y configuracion.
- No siempre cubre con la misma facilidad todos los flujos que un usuario resuelve en pantalla.
- Para algunos clientes, exponer o habilitar un endpoint API puede ser casi tan sensible como abrir acceso tecnico.

#### Nivel de friccion comercial

Medio.

Es menor que pedir acceso directo a HANA/SQL, pero mayor que operar sobre la sesion visual ya autorizada del usuario. Puede activar preguntas del cliente sobre seguridad, infraestructura, permisos, soporte SAP y responsabilidad ante errores.

#### Nivel de robustez

Alto, cuando esta bien configurado.

Service Layer debe ser la direccion preferida para integraciones profesionales, especialmente cuando el cliente ya lo tiene disponible o cuando el caso de uso justifica una configuracion tecnica formal.

#### Certificacion SAP para uso privado autorizado

Para un uso privado autorizado por el cliente, consumir Service Layer no implica automaticamente que Team360 deba venderse como solucion certificada SAP. Lo importante es no posicionarlo como add-on certificado, integracion homologada o producto SAP oficial si no se recorrio ese proceso.

Advertencia: la interpretacion final depende del contrato SAP, licencias del cliente, modalidad de despliegue, pais, partner SAP y alcance comercial. Para producto masivo o add-on distribuible, revisar formalmente certificacion, licencias y terminos SAP.

### B. DI API / SDK local

#### Que es

DI API es parte del SDK de SAP Business One. Permite integrar soluciones externas con SAP B1 usando objetos de negocio y reglas de negocio de SAP, sin consultar directamente tablas HANA/SQL desde Team360.

SAP documenta DI API como una biblioteca COM orientada principalmente a Microsoft Visual C/C++, Visual Basic y Microsoft .NET. Esto condiciona la arquitectura recomendada.

#### Que necesita

- Windows local o VM Windows.
- SAP Business One SDK / DI API instalado.
- Usuario SAP autorizado.
- Datos de conexion a la compania SAP B1.
- Licenciamiento y permisos adecuados.
- Configuracion compatible con la version exacta de SAP B1 del cliente.
- Manejo cuidadoso de COM, threading y ciclo de vida de la conexion.

#### Datos de conexion necesarios

Los datos concretos dependen de la instalacion, pero normalmente se necesita:

- Servidor SAP Business One / License Server.
- Company DB o identificador de compania.
- Tipo de base o backend segun instalacion.
- Usuario SAP.
- Password o mecanismo autorizado por el cliente.
- Parametros regionales/idioma si afectan la operacion.
- Configuracion de red y permisos.

#### Python con pywin32 + COM

Es tecnicamente posible trabajar desde Python usando `pywin32` para invocar COM. Puede servir para pruebas internas o prototipos muy controlados.

No es la recomendacion principal para produccion. DI API se lleva mejor con el ecosistema Windows/.NET, y los errores COM, threading, bitness, instalacion y versionado suelen ser mas manejables desde C#/.NET.

#### Recomendacion fuerte: helper C#/.NET local

Modelo recomendado:

```text
Team360 Python
  -> HTTP local
  -> Helper C#/.NET
  -> DI API
  -> SAP Business One
```

El helper local seria responsable de:

- Encapsular conexion DI API.
- Ejecutar operaciones permitidas.
- Normalizar errores SAP.
- Registrar logs tecnicos.
- Exponer una API local pequena y controlada.
- Evitar que el backend Python tenga que convivir directamente con COM.

#### Ventajas contra RPA

- Menor dependencia de pantalla, foco, resolucion e idioma visual.
- Mejor control de errores de negocio.
- Mejor repetibilidad.
- Mejor trazabilidad tecnica.
- Mas adecuado para escrituras controladas.
- Puede correr de forma mas estable en una VM/PC dedicada.

#### Desventajas

- Mayor friccion tecnica inicial.
- Requiere DI API instalada y compatible.
- Requiere conocimiento SAP B1 SDK.
- Puede requerir licencias/usuarios adecuados.
- La DI API no es ideal para todo tipo de extraccion masiva.
- No conviene usarla como primer paso comercial si el cliente todavia no confia o no quiere configurar nada.

#### Casos de uso recomendados

- Crear o actualizar documentos con aprobacion y validaciones previas.
- Consultar objetos de negocio de forma estructurada.
- Procesos recurrentes donde la pantalla es fragil.
- Automatizaciones que ya demostraron valor con RPA y justifican robustez.
- Integraciones donde el cliente acepta instalar componentes locales.

### C. RPA Desktop sobre SAP Business One Client

#### Que es

Automatizacion de escritorio sobre el SAP Business One Desktop Client. El worker interactua con la interfaz grafica como lo haria un usuario: detecta ventanas/controles, escribe, hace clic, lee estados, toma screenshots y registra logs.

#### Que necesita

- SAP Business One Client instalado.
- Windows con sesion activa.
- Usuario SAP logueado.
- Resolucion fija.
- Worker local corriendo dentro de la misma sesion.
- Permisos del usuario suficientes para las pantallas y acciones requeridas.
- Politica clara de supervision y aprobacion humana.

#### Herramientas posibles

- Python + `pywinauto`
- Python + `pyautogui`
- AutoHotkey
- Power Automate Desktop
- UiPath

#### Recomendacion para MVP

Para un MVP Team360, usar:

```text
Python + pywinauto + screenshots + logs
```

Motivo:

- Permite detectar controles Windows cuando estan disponibles.
- Es suficientemente flexible para prototipos.
- Se integra naturalmente con workers Python.
- Evita arrancar con licencias y complejidad de suites RPA enterprise.
- Permite capturar evidencia visual ante errores.

Fallback:

```text
pyautogui/OCR solo si pywinauto no detecta controles confiables.
```

El fallback por coordenadas, imagen u OCR debe tratarse como menos robusto y usarse en flujos acotados.

#### Ventajas

- Menor friccion comercial inicial.
- No requiere acceso directo a HANA/SQL.
- No requiere configurar Service Layer al inicio.
- Puede usar el usuario SAP existente del cliente.
- Permite validar valor rapido.
- Funciona incluso cuando el flujo real del cliente vive en pantallas, reportes o add-ons visuales.
- Buena opcion para servicio asistido, no para producto autonomo universal.

#### Riesgos

- Fragilidad ante cambios de pantalla, resolucion, foco o popups.
- Dependencia de sesion Windows activa.
- El usuario puede interferir moviendo mouse/teclado.
- Cierre de RDP puede afectar la sesion si no se configura correctamente.
- Errores de negocio SAP aparecen en UI y deben capturarse.
- Auditoria debe ser construida por Team360 con logs y screenshots.
- No sirve para procesos criticos sin supervision al inicio.

#### Casos donde sirve

- Consultas repetitivas.
- Carga asistida con aprobacion humana.
- Descarga de reportes.
- Validaciones operativas.
- Pre-carga de documentos.
- Copiar datos desde WhatsApp/Excel/formularios hacia SAP.
- Procesos donde el usuario hoy ya opera manualmente y se busca reducir tiempo.

#### Casos donde no conviene

- Facturacion automatica sin supervision.
- Pagos.
- Asientos contables.
- Cambios masivos de precios.
- Procesos nocturnos 24/7 desde el primer dia.
- Operaciones irreversibles.
- Procesos con pantallas muy customizadas e inestables.
- Ambientes donde no se puede controlar sesion, resolucion o foco.

## 3. Modelo especifico con escritorio remoto/RDP

El modelo de menor friccion comercial es operar dentro de una sesion Windows autorizada por el cliente.

Flujo:

1. El cliente se conecta por escritorio remoto.
2. Abre SAP Business One con su usuario.
3. El worker Team360 corre dentro de esa misma sesion Windows.
4. El worker automatiza la pantalla usando la sesion SAP ya autorizada.
5. El usuario puede supervisar, aprobar o detener el proceso.
6. Team360 registra resultados, logs y screenshots.

Diagrama:

```text
Usuario cliente
  -> RDP / Escritorio remoto
  -> SAP B1 Client con usuario del cliente
  -> Worker Team360 local
  -> Ejecucion asistida
  -> Resultado / logs / screenshots
  -> Team360
```

### Por que reduce friccion

- Evita pedir al inicio usuario SAP BOT adicional.
- Evita pedir licencia SAP adicional en la primera prueba.
- Evita solicitar roles nuevos de entrada.
- Evita pedir acceso directo a HANA/SQL.
- Evita abrir APIs antes de demostrar valor.
- Usa el mismo marco operativo que el cliente ya acepta: su usuario y sus permisos.

### Limite tecnico y comercial

Este modelo no debe venderse como automatizacion autonoma 24/7.

Es automatizacion asistida/supervisada. Sirve para validar valor, reducir tiempos y construir confianza. Para autonomia real hay que evolucionar hacia VM dedicada, usuario tecnico/BOT, DI API o Service Layer.

## 4. Posicionamiento comercial correcto

### No vender como

- Solucion SAP certificada.
- Add-on SAP oficial.
- Integracion homologada SAP.
- Robot autonomo universal.
- Reemplazo total de operador SAP.
- Integracion directa a base de datos.
- Modificacion del core SAP.

### Vender como

- Automatizacion asistida sobre sesion SAP autorizada.
- Servicio privado bajo aprobacion del cliente.
- Operacion con permisos existentes del usuario.
- Sin acceso directo a base de datos.
- Sin modificacion del core SAP.
- Con trazabilidad, logs y aprobacion humana.
- Camino gradual hacia integraciones mas robustas.

### Frase comercial sugerida

> Implementamos automatizaciones asistidas sobre SAP Business One utilizando la sesion autorizada del usuario, sin acceder directamente a la base de datos ni modificar el core del ERP. El sistema opera dentro del entorno del cliente, con trazabilidad, logs y supervision humana cuando el proceso lo requiere.

## 5. Comparativa ejecutiva

| Opcion | Velocidad de salida | Robustez | Friccion comercial | Riesgo tecnico | Necesita usuario SAP adicional | Necesita acceso HANA/SQL | Mejor uso inicial |
|---|---|---|---|---|---|---|---|
| Service Layer | Media | Alta | Media | Medio | No necesariamente; depende del esquema de permisos y operacion | No | Integraciones API cuando el cliente ya tiene Service Layer disponible |
| DI API / SDK local | Media-baja | Alta | Media-alta | Medio | Puede requerir usuario/licencia adecuados segun operacion | No | Escritura controlada y procesos estructurados con helper local |
| RPA Desktop en sesion del usuario | Alta | Baja-media | Baja | Medio-alto | No al inicio, si se usa el usuario autorizado existente | No | MVP comercial, consultas, descargas, pre-cargas y validacion de valor |
| RPA Desktop con VM dedicada + usuario BOT | Media | Media | Media | Medio | Si, recomendado para autonomia y separacion operativa | No | Procesos repetitivos mas estables, con menor interferencia humana |

## 6. Recomendacion de fases

### Fase 1 - RPA Desktop asistido en sesion del usuario por RDP

Objetivo: salir rapido y validar valor comercial.

Casos:

- Consultas.
- Carga asistida.
- Descarga de reportes.
- Copiar datos desde WhatsApp/Excel a SAP.
- Preparacion de pedidos simples.
- Validaciones repetitivas.

Criterio de exito:

- El cliente ve ahorro operativo real.
- Los flujos son cortos, repetibles y observables.
- Hay logs y screenshots suficientes para auditar errores.
- Toda escritura sensible requiere aprobacion humana.

### Fase 2 - VM o PC dedicada

Objetivo: mas estabilidad.

Agregar:

- Usuario Windows dedicado.
- Sesion controlada.
- Resolucion fija.
- Worker persistente.
- Logs y screenshots.
- Politica de reinicio y recuperacion.
- Checklist de estado antes de ejecutar.

Beneficio:

- Menor interferencia del usuario.
- Mejor repetibilidad.
- Base para agenda de tareas y supervision remota.

### Fase 3 - Usuario SAP BOT o usuario tecnico

Objetivo: automatizacion mas autonoma.

Agregar:

- Permisos minimos.
- Roles especificos.
- Tareas recurrentes.
- Procesos nocturnos.
- Separacion clara entre operador humano y automatizacion.
- Auditoria por usuario tecnico.

Beneficio:

- Mejor control operativo.
- Menor dependencia del usuario final.
- Mayor capacidad de ejecucion recurrente.

### Fase 4 - DI API / Service Layer

Objetivo: robustez profesional.

Agregar:

- Helper .NET para DI API.
- Integracion API.
- Menor dependencia de pantalla.
- Escritura controlada en SAP.
- Contratos de operacion versionados.
- Manejo mas estructurado de errores SAP.

Beneficio:

- Integraciones mas mantenibles.
- Mejor escalabilidad tecnica.
- Menor fragilidad visual.
- Camino natural hacia producto mas formal.

## 7. Alcance inicial recomendado

### Procesos recomendados para MVP

- Consultar stock.
- Consultar cliente.
- Consultar deuda.
- Consultar estado de pedido.
- Descargar reporte.
- Cargar pedido simple con aprobacion humana.
- Copiar datos desde Excel/WhatsApp a SAP.
- Generar borrador o pre-carga.
- Validar campos obligatorios antes de que el usuario confirme.
- Preparar datos para revision humana.

### Procesos NO recomendados al inicio

- Facturacion automatica.
- Pagos.
- Cambios de precios.
- Asientos contables.
- Modificaciones masivas.
- Procesos sin supervision humana.
- Operaciones criticas irreversibles.
- Cambios de maestros sensibles sin aprobacion.
- Automatizaciones que dependan de pantallas inestables o customizaciones no relevadas.

## 8. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigacion |
|---|---|---|
| Usuario mueve la pantalla o usa mouse/teclado | Interrumpe el flujo RPA | Worker dentro de sesion controlada, aviso visual de ejecucion, procesos cortos, bloqueo operativo acordado durante la tarea |
| Cierre de sesion RDP | Corta o degrada automatizacion | Configuracion de sesion persistente, VM/PC dedicada en fase 2, check de estado antes de ejecutar |
| Cambio de resolucion | Rompe coordenadas o deteccion visual | Resolucion fija, preferir pywinauto por controles, fallback visual acotado |
| SAP bloqueado o deslogueado | No se puede ejecutar | Check inicial de estado, deteccion de login/bloqueo, pedir intervencion humana |
| Popups inesperados | Flujo se desvia | Manejo de popups conocidos, screenshots ante error, abortar en estado desconocido |
| Permisos insuficientes | Error de negocio o acceso denegado | Validacion previa de permisos, matriz de operaciones permitidas, mensajes claros al cliente |
| Error de negocio SAP | Datos rechazados o inconsistentes | Logs por paso, captura de mensaje SAP, aprobacion humana para escritura, modo dry-run |
| Auditoria debil | Riesgo operativo/comercial | Logs estructurados, screenshots, identificador de tarea, usuario, timestamp y resultado |
| Dependencia de usuario humano | Limita autonomia | Aceptarlo en fase 1; evolucionar a VM, usuario BOT y APIs en fases posteriores |
| Datos sensibles en screenshots/logs | Riesgo de privacidad | Politica de retencion, redaccion cuando aplique, almacenamiento local o cifrado, permisos de acceso |

### Mitigaciones base obligatorias

- Worker corre dentro de la sesion autorizada.
- Check inicial de estado antes de cada tarea.
- Screenshots ante error.
- Logs por paso.
- Procesos cortos y cerrados.
- Aprobacion humana para escritura.
- Modo dry-run cuando exista riesgo.
- Limites por operacion.
- Rollback operativo manual definido.
- Ambiente test cuando exista.

## 9. Arquitectura minima propuesta

### Modulos sugeridos en Team360

```text
backend/modules/sap_b1/
  automation/
    rpa_worker_protocol.py
    task_schema.py
    result_schema.py
  providers/
    rpa_desktop/
    di_api/
    service_layer/
  workflows/
    stock_query.py
    customer_query.py
    sales_order_assisted.py
  docs/
```

Responsabilidades:

- `automation/`: contratos de tarea, resultado, estados, errores y protocolo con workers.
- `providers/rpa_desktop/`: adaptador para worker RPA local.
- `providers/di_api/`: adaptador futuro para helper .NET + DI API.
- `providers/service_layer/`: adaptador futuro para Service Layer.
- `workflows/`: casos de uso orquestados desde Team360.
- `docs/`: documentacion tecnica especifica del modulo SAP B1.

### Arquitectura del worker Windows

```text
team360_sap_worker/
  app/
    main.py
    config.py
    rpa/
      sap_client_controller.py
      selectors.py
      actions.py
      screenshots.py
    api/
      local_server.py
    logs/
    runtime/
```

Responsabilidades:

- `main.py`: ciclo principal del worker.
- `config.py`: configuracion local sin secretos hardcodeados.
- `sap_client_controller.py`: deteccion de ventana SAP, foco, estado inicial y recuperacion simple.
- `selectors.py`: identificadores de controles, textos, ventanas y heuristicas.
- `actions.py`: acciones atomicas de UI.
- `screenshots.py`: evidencia visual y capturas ante error.
- `local_server.py`: API local para recibir tareas desde Team360 o un agente local.
- `logs/`: trazas operativas.
- `runtime/`: archivos temporales, estado de ejecucion, screenshots y lock files.

### Flujo tecnico minimo

```text
Team360 backend
  -> crea tarea SAP B1
  -> envia tarea al worker local
  -> worker valida sesion Windows/SAP
  -> worker ejecuta pasos RPA
  -> worker registra logs/screenshots
  -> worker devuelve resultado estructurado
  -> Team360 muestra estado y solicita aprobacion si aplica
```

## 10. Decision final

Para salir rapido comercialmente:

```text
RPA Desktop asistido en sesion del usuario por RDP.
```

Para escalar tecnicamente:

```text
VM dedicada + usuario Windows controlado + usuario SAP BOT o tecnico.
```

Para robustez profesional:

```text
DI API / Service Layer, con preferencia por helper C#/.NET para DI API cuando haya escritura estructurada.
```

Decisiones explicitas:

- No usar acceso HANA/SQL en esta linea inicial.
- No iniciar con certificacion SAP.
- No prometer autonomia total al principio.
- No vender como solucion SAP certificada.
- No modificar el core SAP.
- No automatizar procesos criticos irreversibles sin supervision humana.
- Validar primero valor comercial con automatizacion asistida.

## 11. Licenciamiento SAP Business One en el modelo propuesto

### Tipos de licencia SAP B1 relevantes

| Tipo | Perfil tipico | Aplica a BOT? |
|---|---|---|
| Professional | Acceso completo a todas las pantallas y objetos de negocio | Si, si el BOT necesita operar sin restricciones |
| Limited | Acceso a funcionalidades especificas definidas en la licencia | Si, si las operaciones del BOT estan acotadas |
| Indirect Access | Acceso indirecto via API (Service Layer) desde sistemas externos | Depende del contrato; consultar con SAP/partner |
| Partner | Licencias para desarrollo y pruebas internas de partners | Si, para entornos de desarrollo y test internos |

### Recomendaciones por fase

**Fase 1** (RPA sobre usuario existente): No requiere licencia SAP adicional. Se usa la sesion y permisos del usuario autorizado del cliente. Es la ruta de menor friccion legal y comercial.

**Fase 2** (VM dedicada): Si la VM usa el mismo usuario Windows pero sesion independiente, revisar si el contrato SAP del cliente permite multiples sesiones del mismo usuario. Algunas licencias SAP B1 limitan sesiones concurrentes.

**Fase 3** (Usuario SAP BOT): Se recomienda una licencia Limited con los roles estrictamente necesarios para las operaciones automatizadas. Gestionar la creacion con el partner SAP o administrador del cliente.

**Fase 4** (DI API / Service Layer): Evaluar si el acceso por API califica como "Indirect Access" segun el contrato SAP vigente. En SAP B1 10.0 Service Layer esta incluido en la instalacion base, pero el licenciamiento por consumo o acceso indirecto puede aplicar segun el acuerdo con SAP.

### Regla practica

> Si el robot opera con el mismo usuario, licencia y pantalla que el operador humano, no agrega riesgo de licenciamiento nuevo. En cuanto el robot tenga identidad propia (usuario BOT, sesion dedicada, API directa), revisar licencia con el partner SAP del cliente antes de implementar.

## 12. Checklist de relevamiento tecnico-comercial para prospectos

Usar esta checklist en la primera conversacion con un cliente potencial para determinar si es apto para Fase 1 y que preparacion requiere.

### Datos basicos del entorno

- [ ] Version de SAP Business One: _____ (v9.x / v10.x / otro)
- [ ] Base de datos: HANA / SQL Server / No sabe
- [ ] Service Layer instalado? Si / No / No sabe
- [ ] Service Layer configurado y accesible desde red interna? Si / No / No sabe
- [ ] Tienen entorno de test o QA? Si / No
- [ ] Partner SAP activo: _____
- [ ] Cantidad de usuarios SAP: _____
- [ ] Add-ons instalados: _____

### Procesos de interes para automatizar

- [ ] Consulta de stock
- [ ] Consulta de clientes / saldo / deuda
- [ ] Estado de pedidos
- [ ] Descarga de reportes
- [ ] Carga de pedidos desde Excel / WhatsApp / formulario web
- [ ] Validacion de datos antes de ingreso al ERP
- [ ] Pre-carga de borradores (ordenes de venta, compras)
- [ ] Otro: _____

### Infraestructura del operador

- [ ] Tienen Windows Server o PC dedicada para automatizacion? Si / No
- [ ] Permiten acceso por RDP / escritorio remoto? Si / No
- [ ] El operador SAP trabaja remoto o local? Remoto / Local
- [ ] Resolucion de pantalla del operador: _____
- [ ] Bloqueo de pantalla por inactividad: Si / No / Tiempo: _____ min
- [ ] El usuario SAP tiene permisos para las pantallas a automatizar? Si / No / No sabe
- [ ] El usuario SAP tiene acceso a los modulos necesarios? Si / No / No sabe

### Aceptacion comercial

- [ ] El cliente entiende que NO es un add-on SAP certificado ni integracion homologada? Si / No
- [ ] El cliente acepta que el robot use su usuario y sesion existente en Fase 1? Si / No
- [ ] El cliente acepta que Team360 genere logs y screenshots como evidencia de ejecucion? Si / No
- [ ] El cliente esta dispuesto a dedicar tiempo para relevamiento inicial y pruebas? Si / No
- [ ] Presupuesto estimado disponible: USD _____
- [ 】Ventana de tiempo esperada para implementacion: _____ semanas

### Criterio de aptitud rapida para Fase 1

Cliente apto si cumple TODOS estos:
1. SAP B1 v10 sobre Windows.
2. Procesos operativos repetitivos identificados concretamente.
3. Acepta modelo de automatizacion asistida (no certificada, no autonoma).
4. Permite RDP o sesion compartida para el worker.
5. Tiene al menos 1 usuario con permisos suficientes en las pantallas objetivo.
6. Entiende y acepta las limitaciones del modelo RPA Desktop.

## 13. Estimaciones de esfuerzo, costo y duracion por fase

### Fase 1 - RPA Desktop asistido

| Concepto | Estimacion |
|---|---|
| Desarrollo del primer flujo (stock, cliente, deuda) | 2-3 semanas |
| Setup del worker + configuracion RDP + pruebas con cliente | 1 semana |
| Documentacion operativa y logs | 3-5 dias |
| Total Fase 1 | 3-5 semanas |
| Costo estimado Team360 (desarrollo + setup) | USD 3,000 - 6,000 |
| Infraestructura (cargo del cliente) | Ninguna; usa PC/sesion existente del operador |

### Fase 2 - VM dedicada

| Concepto | Estimacion |
|---|---|
| Configuracion de VM Windows + sesion persistente + RDP | 1 semana |
| Migracion de flujos existentes a la VM | 1-2 semanas |
| Pruebas de estabilidad y recuperacion | 3-5 dias |
| Total Fase 2 | 2-3 semanas |
| Costo estimado Team360 (configuracion + migracion) | USD 1,500 - 3,000 |
| Infraestructura (cargo del cliente) | VM Windows ~USD 30-80/mes segun proveedor |

### Fase 3 - Usuario SAP BOT

| Concepto | Estimacion |
|---|---|
| Creacion de usuario SAP BOT y asignacion de roles | 3-5 dias (depende del cliente y partner SAP) |
| Separacion de flujos por identidad BOT vs operador humano | 1-2 semanas |
| Pruebas con permisos minimos | 1 semana |
| Total Fase 3 | 2-3 semanas |
| Costo estimado Team360 | USD 2,000 - 4,000 |
| Licencia SAP (cargo del cliente) | Segun acuerdo SAP vigente; recomendar Limited |

### Fase 4 - DI API / Service Layer

| Concepto | Estimacion |
|---|---|
| Desarrollo de helper C#/.NET para DI API | 4-6 semanas |
| Integracion con Service Layer si aplica | 2-4 semanas |
| Migracion de flujos RPA a API (por flujo) | 2-4 semanas cada uno |
| Pruebas de regresion y corte | 2 semanas |
| Total Fase 4 | 6-12 semanas |
| Costo estimado Team360 | USD 8,000 - 15,000 |
| Infraestructura (cargo del cliente) | Helper local + potenciales costos de licenciamiento por acceso indirecto |

### Estructura de costos sugerida para el cliente

| Item | Modalidad |
|---|---|
| Relevamiento inicial + propuesta | Sin cargo |
| Implementacion Fase 1 (setup + primer flujo funcional) | USD 3,000 - 6,000 one-time |
| Flujo adicional (stock, clientes, pedidos, reportes, etc.) | USD 1,000 - 2,500 por flujo |
| Mantenimiento / soporte mensual (monitoreo + actualizaciones) | USD 200 - 500/mes |
| VM dedicada Fase 2 (gestionada por Team360 o por el cliente) | Costo directo del cliente + fee de gestion mensual |

## 14. Plan de monitoreo remoto de workers

### Componentes del monitoreo

**Worker heartbeat:**
- El worker envia un ping periodico al backend Team360 (ej: cada 30 segundos).
- Si el worker no responde en N intervalos consecutivos, se genera una alerta.
- El heartbeat incluye: worker_id, timestamp, estado actual (idle/running/error), ultima tarea completada.

**Logs estructurados:**
- Cada tarea genera un log con: task_id, timestamp de inicio/fin, cada paso ejecutado, resultado final y error si aplica.
- Logs almacenados localmente en `logs/` y sincronizados al backend al finalizar cada tarea o batch.
- Formato recomendado: JSON estructurado con campos estandar (nivel, mensaje, contexto, timestamp).

**Evidencia visual:**
- Screenshot al iniciar la tarea (estado inicial de la pantalla SAP).
- Screenshot al finalizar cada paso critico.
- Screenshot adicional ante cualquier error o estado inesperado.
- Screenshots referenciados por task_id y almacenados en `runtime/screenshots/`.

**Alertas automaticas:**
- Worker caido o sin heartbeat por mas de N segundos.
- Tarea fallida con error no recuperable (timeout, popup desconocido, SAP bloqueado).
- Tarea ejecutandose por mas tiempo del maximo esperado (timeout por tarea configurable).
- Sesion SAP bloqueada, cerrada o deslogueada.
- Umbral de errores consecutivos superado (ej: 3 errores seguidos detienen el worker).

**Canales de alerta:**
- Dashboard interno Team360 con estado en tiempo real.
- Webhook a Slack, Teams o WhatsApp segun acuerdo con el cliente.
- Email de respaldo si el webhook principal falla.

**Dashboard de estado (propuesto):**
- Workers activos / inactivos.
- Tareas completadas, fallidas y en ejecucion (ultimas 24h).
- Historial de errores con screenshot y log asociado.
- Acceso restringido al equipo Team360; el cliente puede acceder a un dashboard resumido si se acuerda.

### Consideraciones de seguridad en monitoreo

- Los logs y screenshots pueden contener datos del cliente (clientes, precios, movimientos). Asegurar cifrado en reposo (disco local) y en transito (HTTPS hacia backend).
- El canal de heartbeat solo debe exponer estado y contadores, no datos de negocio.
- El dashboard debe requerir autenticacion (usuario y contrasena o SSO).
- Politica de retencion sugerida: 30 dias para logs, 7 dias para screenshots. Ajustar con el cliente segun su politica interna.
- El worker debe poder operar sin conectividad a Internet si el cliente lo exige (modo offline con sincronizacion diferida de logs y resultados cuando la conexion se restablezca).

## 15. Plan de rollback operativo detallado

### Principios

1. Toda operacion de escritura sobre SAP debe tener un procedimiento de rollback definido antes de ejecutarse por primera vez.
2. El rollback puede ser automatico (operaciones reversibles) o manual (operaciones que requieren intervencion de un operador SAP del cliente).
3. Modo dry-run obligatorio para toda operacion de escritura nueva antes de pasar a produccion.
4. Sin excepcion: si no hay rollback definido, la operacion no se ejecuta.

### Operaciones de consulta (solo lectura)

No requieren rollback. Si la consulta falla, se registra el error estructurado y se notifica al solicitante. No hay efecto secundario en SAP.

### Operaciones de escritura asistida

#### Pre-carga de pedido (borrador)

| Aspecto | Detalle |
|---|---|
| Riesgo | Datos incorrectos cargados en un borrador de orden de venta, compra o produccion |
| Rollback automatico | Identificar el documento SAP creado, marcarlo como "Pendiente de revision" (no enviar a contabilizacion), registrar en log |
| Rollback manual | Si el cliente rechaza el borrador, eliminarlo desde SAP o marcarlo como cancelado |
| Verificacion | Confirmar que el documento paso a estado "Cancelado" o "Borrador" segun lo acordado |

#### Carga de datos maestro (cliente, proveedor, articulo)

| Aspecto | Detalle |
|---|---|
| Riesgo | Creacion de maestros con datos erroneos (RFC duplicado, denominacion incorrecta, condiciones de pago equivocadas) |
| Rollback automatico | Bloquear el maestro creado (no eliminar) para evitar su uso operativo |
| Rollback manual | Notificar al administrador SAP del cliente para correccion de datos o baja definitiva |
| Restriccion | Nunca eliminar maestros de forma automatica. Requiere intervencion humana siempre |

#### Actualizacion de datos existentes

| Aspecto | Detalle |
|---|---|
| Riesgo | Modificacion de un campo incorrecto (ej: limite de credito, condicion de pago, direccion) |
| Rollback automatico | Antes de modificar, tomar snapshot del valor actual (log + screenshot). Si la modificacion es erronea o rechazada, restaurar el valor original |
| Rollback manual | Si no se puede restaurar automaticamente, notificar al usuario con el valor anterior para que lo corrija manualmente |
| Aprobacion | Toda actualizacion debe ser aprobada por un humano antes de ejecutarse en Fase 1 |

### Operaciones NO sujetas a rollback automatico

Estas operaciones no deben automatizarse en Fase 1 ni Fase 2. Solo considerar en Fase 4 con validacion legal, contable y operativa del cliente, y siempre con aprobacion humana explicita:

- Facturas ya contabilizadas.
- Pagos ejecutados.
- Asientos contables.
- Cambios de precio en maestros.
- Eliminacion fisica de documentos.
- Reversiones de documentos contabilizados.

### Procedimiento general de rollback

```text
1. Detectar error o recibir solicitud explicita de rollback.
2. Identificar el tipo de operacion y el documento/recurso afectado.
3. Ejecutar el paso de rollback segun el tipo (tablas anteriores).
4. Verificar el resultado del rollback (consulta de confirmacion en SAP).
5. Si el rollback automatico falla: escalar a operador humano con datos del error, logs y screenshots.
6. Registrar todo el proceso en log estructurado.
7. Notificar el resultado al solicitante (Team360 y/o cliente).
```

### Checklist pre-ejecucion para operaciones de escritura

Antes de cada operacion de escritura, verificar:

- [ ] Modo dry-run ejecutado sin errores para esta operacion?
- [ ] Datos de entrada validados contra el esquema esperado?
- [ ] Procedimiento de rollback definido y documentado para esta operacion?
- [ ] Usuario humano disponible para aprobar la ejecucion?
- [ ] Limite de tiempo maximo definido para esta operacion?
- [ ] Screenshot del estado inicial tomado y registrado?

### Checklist post-ejecucion

- [ ] Screenshot del estado final tomado y almacenado?
- [ ] Resultado registrado en log estructurado (task_id, timestamp, resultado, error si aplica)?
- [ ] Si la operacion era de escritura: notificacion enviada al usuario solicitante?
- [ ] Si la operacion fallo: rollback ejecutado exitosamente o escalado a operador humano?
- [ ] Datos sensibles redactados en logs y screenshots segun politica acordada?
- [ ] Worker listo para recibir la siguiente tarea? (check de estado post-ejecucion)

## Referencias consultadas

- SAP Help Portal - SAP Business One Service Layer: `https://help.sap.com/docs/SAP_BUSINESS_ONE/f110a154dd0f4c20bf7f3ebca9eeb794/60c7a0b745bd486589f05a1da77041f3.html`
- SAP Help Portal - SAP Business One SDK / DI API: `https://help.sap.com/docs/SAP_BUSINESS_ONE/a2c93a1c88a24f1faeee3d3f62fbde7a/1c66e99da4864964ac11bb74e49786b8.html`
- SAP Help Portal - SAP Business One 10.0 Platform and Extensibility: `https://help.sap.com/docs/SAP_BUSINESS_ONE/2b32d0343c7140a2946d87d77e2c4aac/53312d5360efe844e10000000a423f68.html?version=10.0`
- SAP Help Portal - SAP Business One SDK Licensing: `https://help.sap.com/docs/SAP_BUSINESS_ONE/a2c93a1c88a24f1faeee3d3f62fbde7a/9e7768e321e4454fa5be4b599bc2bf81.html?version=10.0`
- SAP Help Portal - Add-On Identifier Generator: `https://help.sap.com/docs/SAP_BUSINESS_ONE/a2c93a1c88a24f1faeee3d3f62fbde7a/af374dcf6a1e479f874db6645b023a65.html?version=10.0`
