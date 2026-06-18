# Deploy frontend Team360 Live - 2026-06-18

## Alcance aplicado

Produccion inicial queda limitada al frontend estatico de Astro servido por
Nginx.

Dominio:

```text
team360.live
```

Directorio remoto:

```text
/home/administrator/project/iMotorSoft/ai/Team360
```

Directorio servido por Nginx:

```text
/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/astro/dist
```

Ruta publica:

```text
/
```

`/t360` se conserva como ruta de prueba dentro del mismo build. Cuando se cierre
esa prueba, se puede copiar o promover el contenido definitivo a `index`.

## Nginx

Sitio:

```text
/etc/nginx/sites-available/team360.live
/etc/nginx/sites-enabled/team360.live
```

Configuracion esperada:

```nginx
server {
    listen 80;
    server_name team360.live;

    client_max_body_size 50M;

    location / {
        root /home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/astro/dist;
        try_files $uri $uri/ /index.html$is_args$args;

        add_header Cache-Control "no-cache, no-store, must-revalidate";
        add_header Pragma "no-cache";
        add_header Expires "0";
    }

    location /api/ {
        proxy_pass http://localhost:7050;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_buffering off;
    }
}
```

Nota: `/api/` queda preparado para el backend futuro en `127.0.0.1:7050`, pero
el backend no debe arrancarse todavia en esta fase.

## TLS

Certbot quedo aplicado para:

```text
https://team360.live
```

Certificado:

```text
/etc/letsencrypt/live/team360.live/fullchain.pem
/etc/letsencrypt/live/team360.live/privkey.pem
```

Vencimiento informado por Certbot:

```text
2026-09-16
```

Certbot dejo renovacion automatica programada.

## Frontend API URL

Para produccion se ajusto `SrvRestAstroLS_v1/astro/src/components/global.js`
para que `API_BASE_URL` resuelva como ruta relativa:

```text
/api
```

Esto evita que el navegador del usuario final intente llamar a
`http://localhost:7050`.

## Backend pendiente

No activar backend hasta completar preflight y configuracion privada.

La DB remota `team360` ya fue recreada en el contenedor Docker remoto
`imotorsoft-postgres` desde la DB local de desarrollo. Validacion al cierre:
57 tablas publicas y conteos por tabla sin diferencias frente al origen local.

Milvus remoto ya fue alineado con Milvus local para las collections permitidas.
La collection remota `JAI_document_embeddings` fue tratada como protegida y no
fue tocada; mantuvo 3231 entidades antes y despues. La collection productiva
`team360_sales_diagnosis_knowledge_v1` quedo con 183 entidades y busqueda
vectorial basica validada.

Variables no secretas recomendadas para `.bashrc`, entorno del servicio o
archivo privado equivalente:

```bash
AUTOMATION_DIAGNOSIS_REPOSITORY=postgres
TEAM360_AI_PROVIDER=litellm
TEAM360_LITELLM_BASE_URL=http://localhost:4000/v1
TEAM360_LITELLM_MODEL_ALIAS=openai_gpt-5-nano
TEAM360_LITELLM_API_MODE=chat
TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER=milvus
TEAM360_MILVUS_HOST=127.0.0.1
TEAM360_MILVUS_PORT=19530
TEAM360_MILVUS_COLLECTION=team360_sales_diagnosis_knowledge_v1
TEAM360_KNOWLEDGE_SCOPE_ID=8b071443-5bd6-4fe4-bbc3-fc2dca179a5b
TEAM360_EMBEDDING_MODEL=openai_text_embedding_3_small
```

Variables secretas o sensibles que deben venir de entorno privado, no de docs
ni comandos pegados en historial:

```bash
TEAM360_DB_URL_PSQL=postgresql://administrator:***@localhost:5432/team360
TEAM360_LITELLM_API_KEY=***
LITELLM_API_KEY=***
LITELLM_MASTER_KEY=***
OPENAI_API_KEY=***
TEAM360_OPENAI_KEY=***
TEAM360_MILVUS_TOKEN=***
```

Observacion tecnica: `modules/db/settings.py` debe resolver la DSN por la regla
central del proyecto:

1. `TEAM360_DB_URL`.
2. `TEAM360_DB_URL_PSQL`.
3. `DB_PG_V360_URL` derivando la DB `team360`.
4. `globalVar.get_team360_db_url_psql()`.

No imprimir ni documentar el valor real de la DSN cuando contenga password.

## Validaciones esperadas

Frontend/Nginx:

```bash
sudo nginx -t
curl -I -H 'Host: team360.live' http://127.0.0.1/
curl -I -H 'Host: team360.live' http://127.0.0.1/t360/
curl -I https://team360.live/
```

Backend futuro:

```bash
curl http://127.0.0.1:7050/health
curl -H 'Host: team360.live' http://127.0.0.1/api/health
```

Antes de interpretar calidad del asistente, ejecutar el preflight obligatorio
definido en `lat.md/service-preflight-methodology.md`.
