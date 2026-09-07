-- PHASE 2 — SAP USER MASTER (READ ONLY)
-- Inventario completo de usuarios SAP con estado, empleado y vendedor asociados.
-- Schema: TELCHI
-- Grain: USERID (one row per SAP user)

SELECT
    U."USERID",
    U."USER_CODE",
    U."U_NAME",
    U."SUPERUSER",
    U."Locked",
    U."GROUPS",
    U."ALLOWENCES",
    U."DISCOUNT",
    U."SalesDisc",
    U."PurchDisc",
    U."Branch",
    U."Department",
    U."E_Mail",
    U."DfltsGroup",
    U."MobileUser",
    U."lastLogin",
    U."LstLogoutD",
    U."LstLoginT",
    U."LstLogoutT",
    U."FailedLog",
    U."PwdNeverEx",
    U."createDate",
    U."updateDate",
    U."userSign",
    U."userSign2",
    E."empID"          AS "emp_empID",
    E."firstName"      AS "emp_firstName",
    E."lastName"       AS "emp_lastName",
    E."status"         AS "emp_status",
    E."Active"         AS "emp_Active",
    E."salesPrson"     AS "emp_salesPrson",
    E."branch"         AS "emp_branch",
    E."BPLId"          AS "emp_BPLId",
    E."userId"         AS "emp_userId",
    E."jobTitle"       AS "emp_jobTitle",
    E."dept"           AS "emp_dept",
    E."termDate"       AS "emp_termDate",
    S."SlpCode"        AS "slp_SlpCode",
    S."SlpName"        AS "slp_SlpName",
    S."Active"         AS "slp_Active",
    S."Locked"         AS "slp_Locked",
    S."EmpID"          AS "slp_EmpID",
    BR."Name"          AS "branch_Name",
    BR."Code"          AS "branch_Code"
FROM "TELCHI"."OUSR" U
LEFT JOIN "TELCHI"."OHEM" E
    ON E."userId" = U."USERID"
LEFT JOIN "TELCHI"."OSLP" S
    ON S."EmpID" = E."empID"
LEFT JOIN "TELCHI"."OUBR" BR
    ON BR."Code" = U."Branch"
ORDER BY U."USERID"
