# Team360: OpenCode + sudo seguro mediante SUDO_ASKPASS

Clasificacion: `GLOBAL / SHARED OPERATIONAL DOCUMENTATION`

Este procedimiento permite que agentes ejecutados mediante OpenCode realicen
operaciones privilegiadas puntuales sin ejecutar OpenCode como `root`, sin
entregar la contrasena al modelo y sin depender de un TTY interactivo.

Aplica transversalmente a Team360 y a sus agentes, por ejemplo para Podman,
Docker administrativo, systemd, networking, VPN, mounts, permisos,
infraestructura local, deploys y diagnostico del host.

Esta es una herramienta para operacion y desarrollo asistidos por una persona.
No modifica el runtime de ningun modulo ni constituye un mecanismo de
autenticacion para servicios unattended de produccion.

## 1. Contexto

Los agentes de OpenCode pueden ejecutar comandos shell sin disponer de un TTY
interactivo adecuado para introducir una contrasena de `sudo`. En ese contexto,
un comando como:

```sh
sudo -v
```

puede fallar con un error equivalente a `this session has no interactive
terminal for password entry`.

Autenticar previamente en otra terminal con `sudo -v` tampoco garantiza que el
proceso del agente pueda reutilizar correctamente esa autenticacion. Team360
no debe depender como estrategia general de `sudo -v`, `sudo -n`, una cache
previa de sudo, contrasenas en prompts ni contrasenas enviadas por stdin.

## 2. Decision operativa

Para un agente OpenCode que necesite privilegios, utilizar:

```text
SUDO_ASKPASS + sudo -A
```

La contrasena la introduce directamente la persona autorizada mediante un
dialogo grafico local. OpenCode y el modelo solicitan la operacion y ejecutan
`sudo -A <comando>`, pero no conocen, reciben, almacenan, registran ni
imprimen la contrasena.

Flujo:

```text
MODEL
  |
OpenCode
  |
sudo -A
  |
SUDO_ASKPASS
  |
Zenity
  |
USUARIO introduce la contrasena
  |
sudo ejecuta el comando
```

El mecanismo no depende del modelo utilizado: aplica igualmente a GPT,
DeepSeek, Qwen u otros modelos usados mediante OpenCode.

## 3. Helper askpass

Helper validado:

```text
$HOME/.local/bin/sudo-askpass-zenity
```

Contenido:

```sh
#!/bin/sh
exec /usr/bin/zenity --password --title="Autorizacion sudo"
```

El helper no contiene ninguna contrasena; solo abre el dialogo grafico.
Debe ser ejecutable y de uso privado por el usuario:

```sh
chmod 700 "$HOME/.local/bin/sudo-askpass-zenity"
```

Si el helper aun no existe, su creacion y la instalacion de Zenity deben
realizarse como una tarea separada y autorizada. Esta documentacion no las
ejecuta automaticamente.

## 4. Entorno de OpenCode

Antes de iniciar OpenCode desde la terminal del usuario:

```sh
export SUDO_ASKPASS="$HOME/.local/bin/sudo-askpass-zenity"
opencode
```

OpenCode debe ejecutarse como usuario normal. Puede comprobarse la variable
antes de iniciar el agente con:

```sh
printenv SUDO_ASKPASS
```

El valor esperado conceptualmente es:

```text
/home/<usuario>/.local/bin/sudo-askpass-zenity
```

La variable debe existir en el entorno desde el cual se inicia OpenCode. Si el
agente no la recibe, cerrar OpenCode, exportarla en la terminal y volver a
iniciar OpenCode desde esa misma shell.

## 5. Validacion

Antes de una operacion real puede validarse el mecanismo con:

```sh
sudo -k
sudo -A id
```

`sudo -k` invalida deliberadamente credenciales previas y obliga a comprobar
el flujo askpass. Debe aparecer el dialogo grafico. Tras introducir
personalmente la contrasena, el resultado esperado es equivalente a:

```text
uid=0(root) gid=0(root) groups=0(root)
```

Esta prueba valida:

```text
SUDO_ASKPASS_AVAILABLE=PASS
SUDO_ASKPASS_DIALOG=PASS
SUDO_A_PRIVILEGE_ESCALATION=PASS
```

La prueba no debe usarse como sustituto de la autorizacion de una operacion
concreta.

## 6. Uso desde OpenCode

Un prompt que necesite privilegios debe indicar explicitamente que la
operacion concreta utilice:

```sh
sudo -A <comando>
```

Asumir que `SUDO_ASKPASS` ya fue configurado en el entorno no elimina la
necesidad de revisar el comando y autorizar la operacion.

No usar:

- `sudo -n` como mecanismo de autenticacion.
- `sudo -v` como mecanismo de autenticacion del agente.
- `sudo -S`.
- Contrasenas en stdin.
- Contrasenas en prompts.
- Contrasenas en scripts, archivos `.env`, repositorios, historial shell o
  logs del agente.

Nunca pedir, leer, almacenar, registrar ni imprimir la contrasena.

## 7. Ejemplos de uso autorizado

Estos ejemplos son ilustrativos y no deben ejecutarse como parte de esta tarea
documental:

```sh
sudo -A podman pod ps
sudo -A docker <comando>
sudo -A systemctl status <service>
sudo -A systemctl restart <service>
sudo -A ip xfrm state
```

Usar privilegios solo cuando el comando realmente los requiera y cuando la
operacion este explicitamente autorizada.

## 8. Principio de minimo privilegio

No se recomienda ejecutar OpenCode como `root`:

```sh
sudo opencode
```

Eso convierte toda la sesion del agente en una sesion administrativa. Cualquier
comando, escritura, creacion de archivo, script o herramienta secundaria
podria ejecutarse con privilegios elevados.

La estrategia Team360 es:

```text
OpenCode = usuario normal
operacion concreta = sudo -A <comando>
```

## 9. Reglas de seguridad

Queda expresamente prohibido enviar secretos a `sudo` mediante stdin o
incluirlos en instrucciones o artefactos del agente. En particular, no usar:

```sh
echo "PASSWORD" | sudo -S <comando>
printf 'PASSWORD' | sudo -S <comando>
```

Tampoco usar construcciones como `PASSWORD=<password>`, ni guardar valores
reales en prompts, scripts, `.env`, repositorios, historial shell,
documentacion o logs.

El helper puede aparecer documentado; ninguna contrasena real debe aparecer
en Team360.

## 10. Askpass no es para produccion unattended

OpenCode en desarrollo u operacion asistida puede utilizar:

```text
sudo -A + askpass + autorizacion humana
```

Un servicio unattended de produccion no puede depender de una ventana Zenity.
Debe resolver sus permisos mediante una combinacion especifica de permisos
minimos, service accounts, capabilities, systemd, Podman, secretos y
politicas de despliegue, segun corresponda.

No mezclar el agente humano asistido por askpass con un servicio automatico de
produccion.

## 11. Sudoers y NOPASSWD

Esta solucion no requiere modificar inicialmente `/etc/sudoers` ni crear
reglas `NOPASSWD`. No implementar `NOPASSWD` de manera global para facilitar
agentes.

Si un servicio automatico necesitara privilegios unattended en el futuro, debe
ser una decision de seguridad separada y especifica. No mezclarla con este
procedimiento interactivo.

## 12. Troubleshooting

### El helper no puede ejecutarse

Error equivalente:

```text
sudo: unable to run ...sudo-askpass-zenity: No such file or directory
```

Verificar:

```sh
ls -l "$HOME/.local/bin/sudo-askpass-zenity"
```

### Zenity no esta disponible

Verificar:

```sh
command -v zenity
```

No instalar dependencias automaticamente durante una tarea cualquiera;
reportar la dependencia faltante y tratar su instalacion como una tarea
autorizada separada.

### OpenCode no recibe SUDO_ASKPASS

Verificar dentro del entorno del agente:

```sh
printenv SUDO_ASKPASS
```

Si esta vacio, cerrar OpenCode, exportar la variable en la terminal y volver a
iniciar OpenCode desde esa terminal.

### No aparece la ventana

Probar fuera de OpenCode:

```sh
sudo -k
sudo -A id
```

Esto permite distinguir un problema de askpass/escritorio de un problema del
entorno de OpenCode.

## 13. Caso de validacion inicial: Telchi

Telchi es el primer caso real que permitio validar este mecanismo dentro del
contexto Team360. El agente necesitaba consultar y administrar Podman rootful
para desarrollar un runtime strongSwan aislado, pero no disponia de TTY para
`sudo`.

La solucion validada fue:

```text
SUDO_ASKPASS + sudo -A + Zenity
```

Telchi se registra solamente como caso de validacion. Esta politica es global
y no contiene secretos, PSK, XAuth, claves API, contrasenas HANA ni otros
secretos privados de Telchi.

## 14. Alcance y cambios

Esta documentacion es global y compartida para operaciones asistidas de
Team360. No autoriza por si misma ninguna operacion privilegiada.

La adopcion de este procedimiento no modifica:

- Runtime.
- Backend o frontend.
- Dependencias.
- Docker o Podman runtime.
- Networking, systemd o VPN.
- Sudoers.
- DataScience.

Antes de cerrar una tarea documental que use esta politica, revisar los
archivos modificados y confirmar que no contienen valores reales de secretos.
