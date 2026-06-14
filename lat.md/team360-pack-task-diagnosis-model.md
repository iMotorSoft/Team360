# Team360 — Modelo de Packs, Tasks y Diagnostico

## Proposito

Definir el modelo funcional y comercial de Team360 para expresar soluciones configurables, tareas ejecutables, flujos de automatizacion, integraciones y diagnostico.

Este modelo debe servir para producto, diseno, ventas, documentacion tecnica y futuros paquetes de automatizacion.

## Principio central

Team360 no vende solo un chatbot ni un catalogo cerrado.

Team360 diagnostica la operacion real del cliente y traduce la necesidad en una arquitectura posible de solucion.

Esa arquitectura puede incluir:

- T360 Packs;
- T360 Tasks;
- T360 Pack Flows;
- T360 Pack Integrate;
- componentes existentes;
- componentes configurables;
- componentes que requieren desarrollo.

Regla:

> Team360 diagnostica primero, configura despues y automatiza con Packs y Tasks segun la operacion real del cliente.

## T360 Pack

Un T360 Pack es una solucion configurable para una necesidad del cliente.

No debe entenderse como un paquete rigido ni cerrado. Puede adaptarse al contexto, industria, canal, sistema, proceso o madurez operativa del cliente.

Un Pack puede incluir:

- Tasks;
- Pack Flows;
- Pack Integrate;
- reglas de ejecucion;
- configuracion del cliente;
- entradas y salidas esperadas;
- criterios de factibilidad;
- limites comerciales y operativos.

Ejemplos:

- T360 Technical Email Pack;
- T360 Debt WhatsApp Pack;
- T360 Sales Follow-up Pack;
- T360 CRM Operations Pack.

## T360 Task

Una T360 Task es una unidad puntual ejecutable.

Hace una accion concreta dentro de un Pack, un Pack Flow o un Pack Integrate.

Puede recibir datos, transformar informacion, consultar un sistema, generar una respuesta, enviar un mensaje, crear una tarea o producir una salida estructurada.

Ejemplos:

- WhatsApp In;
- Email In;
- Extract Customer ID;
- Extract Document ID;
- Connect SAP;
- Query Debtors by ID;
- Consolidate Debt;
- JSON Response;
- WhatsApp Out;
- Technical Response Draft;
- Prospect Summary;
- Sales Notification.

Regla:

> Task = accion concreta. Pack = solucion funcional.

## T360 Pack Flow

Un T360 Pack Flow es un Pack que automatiza un proceso de punta a punta.

Incluye varias Tasks conectadas y puede invocar Packs Integrate cuando necesita consultar, sincronizar o conectar sistemas externos.

### T360 Debt WhatsApp Pack Flow

Flujo:

1. Task WhatsApp In.
2. Task Extraer ID / Documento.
3. T360 Pack Integrate Consulta SAP Deudores.
4. Task WhatsApp Out.

Objetivo:

Responder consultas de deuda por WhatsApp, desde el mensaje entrante hasta la respuesta al cliente.

## T360 Pack Integrate

Un T360 Pack Integrate es un Pack orientado a conectar sistemas, canales o fuentes de datos.

Puede integrarse con:

- SAP;
- CRM;
- WhatsApp;
- email;
- bases internas;
- APIs externas;
- ERPs;
- sistemas de gestion.

### T360 Pack Integrate Consulta SAP Deudores

Tasks:

1. Task Connect SAP.
2. Task Consulta Deudores por ID.
3. Task Consolidado de Deuda.
4. Task Respuesta JSON.

Este Pack Integrate puede reutilizarse dentro de distintos Pack Flows:

- deudas por WhatsApp;
- deudas por email;
- portal de clientes;
- reporte diario de deudores;
- atencion comercial.

## Modos de ejecucion

Los Packs y Tasks pueden ejecutarse con diferentes modos.

### Scheduled

Corre por agenda definida por el cliente.

Ejemplos:

- revisar emails cada 30 minutos;
- generar reporte diario de prospectos a las 9:00;
- detectar prospectos sin seguimiento cada noche.

### On-Demand

Se ejecuta por accion puntual del usuario.

Ejemplos:

- analizar este email ahora;
- consultar deuda de este cliente;
- generar respuesta tecnica para esta consulta;
- exportar prospectos de esta semana.

### Event-Driven

Se dispara por un evento externo.

Ejemplos:

- entra un WhatsApp;
- llega un email;
- se recibe un webhook;
- cambia el estado de un registro en un sistema.

## Diagnostico Team360

El Diagnostico Team360 es la puerta de entrada inteligente de la plataforma.

Debe entender la necesidad real del cliente y entregar una orientacion practica, no una respuesta generica.

Debe analizar:

- contexto del negocio;
- canal de entrada;
- proceso afectado;
- dolor principal;
- datos disponibles;
- sistemas involucrados;
- factibilidad tecnica;
- factibilidad operativa;
- riesgos;
- prioridad;
- potencial comercial;
- que conviene hacer primero.

El diagnostico no se limita a ventas. Ventas es la entrada comercial inicial, pero el diagnostico debe poder entender necesidades operativas reales de otros dominios.

## Relacion diagnostico -> Packs y Tasks

Una funcion clave del diagnostico es traducir la necesidad del cliente en una posible arquitectura de solucion.

Debe indicar:

- que T360 Pack podria aplicar;
- que T360 Tasks harian falta;
- si corresponde un T360 Pack Flow;
- si requiere un T360 Pack Integrate;
- que componentes existen hoy;
- que componentes se pueden configurar;
- que componentes requieren desarrollo;
- que no conviene vender todavia.

Ejemplo:

Necesidad:

> Mis clientes envian emails preguntando por productos. Quiero que se les responda de forma tecnica y que me envie prospectos.

Posible solucion:

T360 Technical Email Pack

Componentes:

- Task Email In;
- Task Product Inquiry Inspector;
- Task Technical Response Draft;
- Task Prospect Summary;
- Task Sales Notification.

Clasificacion:

- Algunas Tasks pueden existir.
- Otras pueden requerir configuracion con catalogo o base de conocimiento.
- La integracion con CRM o email puede requerir Pack Integrate.
- El diagnostico debe indicarlo con claridad.

## Diagnostico no limitado al catalogo actual

El diagnostico debe ser completo y funcional aunque Team360 todavia no tenga el Pack o la Task exacta.

No debe forzar el problema del cliente a un catalogo cerrado.

Debe clasificar la oportunidad:

### Disponible hoy

Ya existe un Pack, Task, Pack Flow o Pack Integrate aplicable.

### Configurable / armable

Puede armarse combinando componentes existentes.

### Requiere desarrollo

La necesidad es valida, pero requiere una nueva Task, integracion o Pack especifico.

### No conviene vender todavia

Es automatizable, pero no necesariamente prioritario, rentable, maduro o simple de implementar hoy.

Regla:

> Automatizable no significa vendible hoy.

## Alcance comercial prudente

El diagnostico puede mencionar caminos futuros, pero no debe vender como listas capacidades que todavia no estan productivas.

Capacidades futuras ya identificadas:

- Step-to-Action;
- lead capture completo;
- diagnostic_code productivo;
- WhatsApp handoff automatico completo.

Se puede hablar de:

- solicitud de informe completo;
- contacto por WhatsApp;
- interes comercial;
- diagnostico ampliado.

Pero no presentar esas capacidades como producto final si no estan listas.

## Relacion con Home publica y Console

La Home publica de Team360.live es la puerta de entrada comercial prioritaria para ventas, prospectos y feedback.

No debe sentirse como una demo liviana ni solo como landing: debe entregar un diagnostico util, practico y funcional.

La Console queda para una etapa posterior:

- cliente autenticado;
- configuracion de paquetes de automatizacion;
- estado de ejecucion;
- usuarios;
- permisos;
- operacion continua.

El modelo de Packs, Tasks, Flows e Integraciones debe poder expresarse en ambos frentes, pero la primera salida prioriza la Home publica con diagnostico util.

## Frase para diseno/producto

Team360 debe sentirse como una plataforma modular de diagnostico y automatizacion.

El usuario plantea una necesidad real. Team360 diagnostica, ordena y propone una arquitectura de solucion con Packs, Tasks, Flows e Integraciones.

No es un chatbot suelto. No es un catalogo rigido. Es una plataforma que convierte problemas operativos en soluciones configurables.

## Frase de producto

Team360 diagnostica la operacion real del cliente y traduce la necesidad en una arquitectura de solucion con T360 Packs, T360 Tasks, Pack Flows e Integraciones.
