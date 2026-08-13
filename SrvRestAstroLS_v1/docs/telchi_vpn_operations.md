# VPN Telchi: operación FortiClient y strongSwan

Este runbook reúne las dos alternativas IPsec evaluadas para acceder a Telchi desde Team360 sin almacenar secretos ni autenticar todavía contra SAP HANA.

## Alcance y endpoint autorizado

La validación de red se limita al perfil `VPN-TELCHI` y al endpoint actual de SAP HANA 2.

- Perfil: `VPN-TELCHI`.
- Protocolo fuente: IPsec/IKEv1 con PSK y XAuth.
- Usuario XAuth conocido: `insiding_vpn`.
- HANA actual: `192.168.20.20:30015`.
- `192.168.21.4` es una referencia histórica y no debe probarse.
- No autenticar HANA ni ejecutar SQL durante este gate.

## Archivos operativos

El XML externo permanece fuera del repositorio y los scripts contienen solo lógica y parámetros no secretos.

```text
/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/access/fortinet/InsidingConfig.conf.txt
SrvRestAstroLS_v1/scripts/telchi/fortinet/configure.sh
SrvRestAstroLS_v1/scripts/telchi/fortinet/connect-strongswan.sh
SrvRestAstroLS_v1/scripts/telchi/fortinet/validate.sh
```

No modificar el XML, copiarlo al repositorio ni imprimir su contenido completo.

## Tipos de credenciales

Las tres claves del flujo VPN tienen propósitos distintos y no son intercambiables.

- Contraseña de backup/importación: permite importar el XML en FortiClient.
- PSK IKE original: autentica la fase IKEv1; strongSwan lo requiere en texto mediante prompt seguro.
- Contraseña VPN/XAuth: autentica al usuario `insiding_vpn` después de la fase PSK.
- Credenciales SAP HANA: quedan fuera de alcance hasta que el TCP sea PASS.

El XML contiene el PSK como un valor `ENC` propietario. FortiClient puede usarlo después de importar el perfil, pero strongSwan no puede tratar ese bloque cifrado como el PSK original.

## Regla de exclusión entre clientes

FortiClient y strongSwan no deben intentar operar IPsec al mismo tiempo porque pueden competir por UDP 500/4500 y por las políticas XFRM.

Antes de usar FortiClient:

```bash
sudo systemctl stop strongswan.service
```

Antes de usar strongSwan:

```bash
forticlient vpn disconnect VPN-TELCHI
sudo systemctl stop forticlient.service
```

Al terminar una prueba, bajar el cliente usado antes de levantar el otro.

## Alternativa A: FortiClient

Esta es la alternativa que consume directamente el perfil recibido y su PSK cifrado.

### Estado observado

La prueba del 2026-08-13 importó exactamente un perfil, pero EMS bloqueó la conexión antes de XAuth, IKE e IPsec.

- FortiClient `8.0.0.0055`: instalado.
- Perfil `VPN-TELCHI`: importado.
- Servicio: operativo cuando se inicia manualmente.
- Bloqueo: `IPsec VPN is disabled while registered to EMS`.
- XML fuente: IKEv1.
- Vista del perfil importado: IKEv2; esta discrepancia debe revisarse sin editar el XML arbitrariamente.

### Levantar el servicio

El servicio puede iniciarse solo para la ventana de prueba.

```bash
sudo systemctl start forticlient.service
systemctl is-active forticlient.service
```

Para habilitarlo también al arrancar el sistema:

```bash
sudo systemctl enable --now forticlient.service
```

### Importar y conectar

El script es idempotente: importa solo si falta el perfil y pide las claves mediante TTY.

```bash
SrvRestAstroLS_v1/scripts/telchi/fortinet/configure.sh
```

La conexión directa, cuando el perfil ya existe, es:

```bash
forticlient vpn connect VPN-TELCHI --username insiding_vpn
```

No agregar passwords al comando, al environment persistente ni a archivos.

### Consultar estado

Estos comandos verifican perfil y sesión sin acceder a SAP HANA.

```bash
forticlient vpn list
forticlient vpn view VPN-TELCHI
forticlient vpn status
```

Si aparece el bloqueo EMS, detener el intento y solicitar que el administrador habilite IPsec para el endpoint. No desregistrar EMS automáticamente.

### Desconectar y bajar

Primero se desconecta el perfil y luego, si no se usará FortiClient, se detiene su servicio.

```bash
forticlient vpn disconnect VPN-TELCHI
sudo systemctl stop forticlient.service
```

Para impedir el inicio automático:

```bash
sudo systemctl disable --now forticlient.service
```

## Alternativa B: strongSwan headless

Esta alternativa evita la política local de FortiClient/EMS, pero exige disponer del PSK IKE original además de la contraseña XAuth.

### Paquetes instalados

Ubuntu 24.04 usa el daemon `charon-systemd`, `swanctl` y los plugins adicionales que incluyen XAuth genérico.

```bash
sudo apt-get update
sudo apt-get install -y charon-systemd strongswan-swanctl libcharon-extra-plugins
```

La instalación realizada usa strongSwan `5.9.13`.

### Levantar y bajar el servicio

El servicio puede mantenerse deshabilitado y levantarse únicamente durante la prueba.

```bash
sudo systemctl start strongswan.service
systemctl is-active strongswan.service
```

Para detenerlo:

```bash
sudo systemctl stop strongswan.service
```

Para habilitar o deshabilitar el inicio automático:

```bash
sudo systemctl enable --now strongswan.service
sudo systemctl disable --now strongswan.service
```

### Conectar

El conector traduce en memoria gateway, IKEv1, proposals, DH, ModeConfig y selectors del XML; no persiste credenciales.

```bash
SrvRestAstroLS_v1/scripts/telchi/fortinet/connect-strongswan.sh
```

El primer prompt solicita el PSK IKE original. El segundo solicita la contraseña VPN/XAuth. No usar la contraseña de backup ni credenciales HANA como PSK.

El flujo strongSwan sigue experimental y no tiene PASS end-to-end mientras no se disponga del PSK original.

### Consultar sesión y políticas

strongSwan es policy-based y puede no crear una interfaz `tun` o `ppp`; las SAs y políticas XFRM son la evidencia primaria.

```bash
sudo swanctl --list-sas
sudo swanctl --list-pols
sudo ip xfrm state
sudo ip xfrm policy
ip -4 route show table 220
ip -4 route get 192.168.20.20
```

No considerar la ruta válida si sigue saliendo por la interfaz o gateway de la red local sin una SA/política IPsec activa.

### Desconectar y bajar

La sesión se termina por nombre de IKE y luego se detiene el daemon si finalizó la prueba.

```bash
sudo swanctl --terminate --ike vpn-telchi
sudo systemctl stop strongswan.service
```

Detener el servicio elimina las SAs y políticas runtime, pero conserva los paquetes instalados.

## openfortivpn no aplica

`openfortivpn` implementa Fortinet SSL-VPN mediante PPP/TLS y no consume perfiles IPsec/IKEv1 con PSK + XAuth.

No instalarlo ni convertir el perfil Telchi a su formato. La alternativa libre compatible evaluada es strongSwan.

## Validación de red y HANA

La validación debe ejecutarse primero sin credenciales HANA y solo contra el endpoint actual autorizado.

### Gate FortiClient

El script vigente detecta sesiones e interfaces FortiClient y ejecuta el TCP únicamente si confirma ruta por el túnel.

```bash
SrvRestAstroLS_v1/scripts/telchi/fortinet/validate.sh
```

Debe informar el target exacto:

```text
SAP HANA TARGET    192.168.20.20:30015
```

### Gate strongSwan

El script `validate.sh` todavía es específico de FortiClient; para strongSwan se validan primero SAs, XFRM y tabla 220.

```bash
sudo swanctl --list-sas
sudo swanctl --list-pols
sudo ip xfrm state
sudo ip xfrm policy
ip -4 route show table 220
ip -4 route get 192.168.20.20
```

Solo con SA y ruta IPsec confirmadas se permite una única prueba TCP no destructiva:

```bash
nc -vz -w 5 192.168.20.20 30015
```

No probar otros hosts, otros puertos, la IP histórica ni realizar port scanning.

## Interpretación del TCP

El resultado TCP debe clasificarse sin asumir automáticamente que el cliente VPN está fallando.

- `PASS`: host y puerto HANA alcanzables por la VPN.
- `NO_ROUTE`: falta SA, política o routing VPN.
- `HOST_UNREACHABLE`: problema de ruta o infraestructura remota.
- `TIMEOUT`: posible firewall, ruta o servicio sin respuesta.
- `CONNECTION_REFUSED`: host alcanzable, pero puerto o servicio no disponible.

No autenticar HANA, cargar drivers ni ejecutar SQL aunque el TCP sea PASS.

## Ejecución en servidor sin GUI

Ambas alternativas se operan desde una sesión SSH con TTY para que los prompts ocultos funcionen.

```bash
ssh -t usuario@servidor
cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360
```

No enviar claves por chat, pegarlas en comandos, guardarlas en shell history ni incorporarlas a scripts o documentación.

## Diagnóstico actual y próximo paso

El gate de red permanece bloqueado hasta resolver una de las dos condiciones externas.

- FortiClient: EMS debe permitir IPsec y debe revisarse la discrepancia IKEv1/IKEv2.
- strongSwan: Telchi debe entregar el PSK IKE original de forma segura.
- Después: confirmar SA/túnel, ruta a HANA y TCP `192.168.20.20:30015`.
- Recién con TCP PASS comienza el gate separado de driver y autenticación SAP HANA.
