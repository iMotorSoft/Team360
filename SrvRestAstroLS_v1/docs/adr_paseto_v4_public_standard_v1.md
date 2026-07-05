# ADR — PASETO v4.public como estándar Team360

**Fecha:** 2026-07-05
**Estado:** APROBADO
**Rama:** `feature/console-backend-core`

---

## Decisión

```
Team360 adopta PASETO v4.public como estándar para tokens firmados propios.
JWT no se usará salvo integración externa obligatoria.
HMAC embed actual queda como compatibilidad transitoria.
```

## Motivos

- **Proyecto nuevo** — no hay legado JWT que migrar. Se puede elegir el estándar correcto desde el inicio.
- **Menor riesgo de mala configuración** — PASETO no tiene algoritmo negotiation, no permite `alg=none`, no depende de headers JOSE. La versión (`v4.public`) fija Ed25519.
- **Firma asimétrica** — separación private/public key permite verificar tokens sin exponer la clave que los firma.
- **Mejor base para Console** — futuros tokens de admin, service-to-service, magic links e invitaciones se benefician de un formato portable y verificable.
- **HMAC embed es transitorio** — el HMAC-SHA256 request-bound actual funciona, pero no debe ser el contrato final. PASETO permitirá tokens con claims explícitos (client_id, origin, session_id) sin depender de secret compartido.

## No decisión

- No se reemplaza todo en esta fase.
- No se elimina HMAC todavía.
- No se cambia el snippet público todavía.
- No se cambia `/t360`, Vera, ni runtime conversacional.

## Política

1. **Nuevos tokens portables Team360 deben usar PASETO v4.public.**
2. **HMAC solo queda para compatibilidad transitoria del embed actual.** No diseñar nuevas features sobre HMAC.
3. **Cualquier nueva auth de Console debe diseñarse con PASETO.**
4. **La private key nunca llega al frontend.** La public key puede distribuirse para verificación opcional.
5. **Todo token debe incluir:** `iss`, `iat`, `exp`, `jti`, `kid` (vía footer), `typ`.
6. **Las claves se almacenan fuera del repositorio**, via secret manager o filesystem protegido.

## Riesgos

| Riesgo | Mitigación |
| ------ | ---------- |
| Madurez de librería PASETO Python | Validar `pyseto` contra test vectors oficiales. Tener `cryptography` + Ed25519 como respaldo. |
| Rotación de claves | Diseñar con `kid` desde el inicio. Script de rotación. |
| Almacenamiento de private key | Secret manager + env `TEAM360_PASETO_V4_PRIVATE_KEY_PATH`. No inline en código. |
| Revocación | Blacklist en DB o TTL corto + refresh token. |
| Replay de token | `jti` + `exp` + binding a origin en casos sensibles. |
| Clock skew | Tolerancia configurable (±30s). |
| Logs accidentales | `__repr__` sanitizado, no loguear payload completo. |

## Referencias

- [PASETO Specification](https://github.com/paseto-standard/paseto-spec)
- [PASETO v4.public](https://github.com/paseto-standard/paseto-spec/blob/master/docs/01-Protocol-Versions/Version4.md)
- [pyseto — Python library](https://github.com/seansolutions/pyseto)
- [Inventario y factibilidad PASETO](paseto_v4_public_inventory_feasibility_v1.md)
- [Plan de migración embed auth HMAC → PASETO](paseto_embed_auth_migration_plan_v1.md)
