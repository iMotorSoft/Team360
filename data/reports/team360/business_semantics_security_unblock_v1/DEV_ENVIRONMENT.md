# Destino DEV

Existe una instancia local designada DEV y físicamente distinta del PostgreSQL que resuelve el Srv01 productivo oficial. No se necesita aprovisionar otra base para esta comparación.

## Decisión

Se reutiliza el destino existente; no se modifica configuración ni se habilitan operaciones mutables dentro de esta tarea.

Destino local: localhost:5432/team360, cluster 7630993354699489317. Destino oficial productivo: cluster 7559180602161319971 en el host remoto. Evidencia y límites: [DATABASE_BOUNDARY.md](DATABASE_BOUNDARY.md).

La propuesta antigua team360_dev:54329 en docs/team360_postgres_dev_setup.md no es infraestructura disponible: docker ps -a no encuentra ese contenedor; el inventario PG no contiene team360_dev. El [setup histórico](../../../../SrvRestAstroLS_v1/docs/postgresql_live_team360_setup.md) registra que esa base fue eliminada. No ejecutar sus comandos PG16, resets o credenciales de ejemplo.

No crear otra DB en imotorsoft-postgres como sustituto de acreditación. El destino DEV existente tampoco resuelve automáticamente RBAC, autenticación, RLS o privilegios.

## Configuración y retorno

No se cambiaron variables persistidas ni launchers; no hay rollback de configuración que ejecutar.

Los mecanismos actuales son TEAM360_DB_URL explícita y el override privado SrvRestAstroLS_v1/.env.backend-dev.local. Si se prepara posteriormente un runtime Srv05 controlado, verificar host/puerto/DB/rol/system_identifier desde su conexión real, no sólo desde una shell o TEAM360_ENV.

Conservar copia privada del override anterior y registrar presencia de variables sin valores secretos. Restaurar sólo las variables cambiadas en el proceso propio, finalizar ese proceso mediante su lifecycle y verificar el destino anterior read-only. No borrar bases/volúmenes ni reiniciar servicios compartidos.

## Riesgos pendientes

La segregación física comprobada no convierte el estado actual en readiness operacional.

5432 está publicado en 0.0.0.0 y ::; no se auditó firewall, ingress remoto ni todos los consumidores. No se cambió exposición de red. La instancia comparte varios proyectos locales y el rol administrator es globalmente privilegiado. No copiar datos/secretos productivos ni adoptar roles de otros proyectos.

Próximo paso seguro: coordinar ownership Auth/DB para las dos dependencias descritas en [GATES.md](GATES.md); después iniciar sólo un runtime propio con destino pinneado y sin automatización ajena.
