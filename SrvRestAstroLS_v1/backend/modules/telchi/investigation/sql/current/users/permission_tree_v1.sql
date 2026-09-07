-- PHASE 4 — ROLES / GROUPS / PERMISSIONS (READ ONLY)
-- Extracts the authorization model: permission tree, user groups,
-- user→group assignments, group permissions, user direct permissions.

-- Q1: Permission tree (OUPT) — the full hierarchy of SAP B1 permissions
SELECT
    P."AbsId",
    P."Name",
    P."Options",
    P."FathId",
    P."VisOrder",
    P."Levels",
    P."IsItem",
    P."Action"
FROM "TELCHI"."OUPT" P
ORDER BY P."AbsId"
