# TELCHI — HR / PAYROLL / ACCOUNTING TRACEABILITY V1

**Gate:** `TELCHI_HR_PAYROLL_ACCOUNTING_TRACEABILITY_V1_PASS`\
**Modo:** INVESTIGATION / READ ONLY / `SAP_WRITE_COUNT=0`\
**Corte HANA:** `2026-09-10`

## A. VEREDICTO EJECUTIVO

La evidencia observada demuestra que SAP contiene OHEM y el costo laboral que llega al GL; no se identificó un objeto SAP de payroll detallado entre los objetos candidatos inspeccionados. Por tanto, la nómina detallada no se afirma como almacenada en SAP y queda preparada la reconciliación de payroll externo contra GL/pasivo/banco.

## B. UNIVERSO EMPLEADOS

OHEM: **490** · ACTIVE **465** · INACTIVE **25** · TERMINATED **0** · UNRESOLVED **0**. La regla de estado está explicitada en HR02.

## C. ESTRUCTURA ORGANIZACIONAL

Se preservan departamento, branch, cargo, manager, BPLId y CostCenter desde OHEM. La cobertura agregada está en `links`; no se infiere sucursal por usuario.

## D. EMPLEADO ↔ USUARIO SAP

{'EMPLOYEES': 490, 'WITH_USER': 33, 'WITHOUT_USER': 457, 'VALID_USER_LINK': 33, 'SUPERUSER_LINKS': 2, 'ACTIVE_USER_LINKS': 18}; usuarios SAP sin empleado: {'USERS_WITHOUT_EMPLOYEE': 139}.

## E. EMPLEADO ↔ VENDEDOR

{'EMPLOYEES': 490, 'WITH_SALESPERSON': 201, 'VALID_SALESPERSON_LINK': 201}; vendedores sin empleado: {'SALESPERSONS_WITHOUT_EMPLOYEE': 253}.

## F. MODELO DE NÓMINA

No payroll detail is declared from a table name alone; a strong object needs employee/pay-period/pay amount fields and rows. OHEM remains employee master, not payroll history. El gate no afirma nómina detallada por empleado sin objeto transaccional y reconciliación al GL.

## G. CUENTAS RRHH

| Cuenta | Nombre | Clase | Líneas | Neto YTD | Neto histórico | Evidencia |
|---|---|---|---:|---:|---:|---|
| 1110100 | CAJA MONEDA NACIONAL | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110101 | Caja General Tesoreria MN | UNRESOLVED | 64207 | 93052.94 | 211063.64 | HR vocabulary without reliable account class |
| 1110102 | Caja Recaudaciones Terbol | UNRESOLVED | 3558 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110103 | Caja Multired - Sintesis | UNRESOLVED | 7 | 0.0 | 35000.0 | HR vocabulary without reliable account class |
| 1110200 | CAJA SALONES | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110201 | Cajas Casa Matriz MN | UNRESOLVED | 599472 | 4247.75 | 16047.75 | HR vocabulary without reliable account class |
| 1110202 | Cajas 2do. Anillo MN | UNRESOLVED | 340801 | 2030.33 | 12230.33 | HR vocabulary without reliable account class |
| 1110203 | Cajas Villa MN | UNRESOLVED | 177467 | 1206.48 | 3606.48 | HR vocabulary without reliable account class |
| 1110204 | Cajas Urubo MN | UNRESOLVED | 1565 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110205 | Cajas Corporativa 2do. Anillo MN | UNRESOLVED | 32006 | 49947.19 | 49947.19 | HR vocabulary without reliable account class |
| 1110206 | Cajas Roca Coronado MN | UNRESOLVED | 113842 | 1482.73 | 3282.73 | HR vocabulary without reliable account class |
| 1110207 | Cajas Corporativa 2do. Anillo MN - Ventas Especiales | UNRESOLVED | 2118 | 2637.39 | 2637.39 | HR vocabulary without reliable account class |
| 1110300 | CAJAS LABORATORIO | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110301 | Caja Corporativa Laboratorio MN | UNRESOLVED | 31932 | 42808.3 | 42808.3 | HR vocabulary without reliable account class |
| 1110302 | Caja Corporativa La Paz MN | UNRESOLVED | 6992 | 2020.4 | 2020.4 | HR vocabulary without reliable account class |
| 1110303 | Caja Cobranzas MN | UNRESOLVED | 253 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110304 | Caja Distribuidor Placa 4702-GIP MN | UNRESOLVED | 22064 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110305 | Caja Distribuidor Placa 4702-GKT MN | UNRESOLVED | 23390 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110306 | Caja Distribuidor Placa 5260-PSF MN | UNRESOLVED | 18075 | 670.0 | 670.0 | HR vocabulary without reliable account class |
| 1110307 | Caja Distribuidor Placa 2904-ILA MN | UNRESOLVED | 9033 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110308 | Caja Distribuidor Placa 3872-XRI MN | UNRESOLVED | 8604 | 30282.0 | 30282.0 | HR vocabulary without reliable account class |
| 1110309 | Caja Distribuidor Placa 1245-XLN MN | UNRESOLVED | 8608 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110310 | Caja Distribuidor Placa 2725-PRC MN | UNRESOLVED | 17506 | 11442.37 | 11442.37 | HR vocabulary without reliable account class |
| 1110311 | Caja Distribuidor Placa 4474-CDE MN | UNRESOLVED | 126 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110312 | Caja Distribuidor Placa 5687-SPE MN | UNRESOLVED | 7113 | 3112.77 | 3112.77 | HR vocabulary without reliable account class |
| 1110313 | Caja Distribuidor Provincias MN | UNRESOLVED | 740 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110314 | Caja Distribuidor 11 MN LPZ | UNRESOLVED | 17606 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110315 | Caja Distribuidor Placa 5260 IHY MN | UNRESOLVED | 7825 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110316 | Caja Distribuidor Externo 1 | UNRESOLVED | 1208 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110317 | Caja Distribuidor Placa 600-KCI LPZ | UNRESOLVED | 4749 | 7510.81 | 7510.81 | HR vocabulary without reliable account class |
| 1110400 | CAJA MONEDA EXTRANJERA | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110401 | Caja General Tesoreria ME | UNRESOLVED | 1308 | 253106.4 | 423174.4 | HR vocabulary without reliable account class |
| 1110500 | CAJA SALONES ME | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110501 | Cajas Casa Matriz ME | UNRESOLVED | 89 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110502 | Cajas 2do. Anillo ME | UNRESOLVED | 123 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110503 | Cajas Villa ME | UNRESOLVED | 36 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110504 | Cajas Urubo ME | UNRESOLVED | 6 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110505 | Cajas Corporativa 2do. Anillo ME | UNRESOLVED | 95 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110506 | Cajas Roca y Coronado ME | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110600 | CAJAS LABORATORIO M/E | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110601 | Caja Corporativa Laboratorio ME | UNRESOLVED | 48 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110602 | Caja Corporativa La Paz ME | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110603 | Caja Cobranzas ME | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110604 | Caja Distribuidor Placa 4702-GIP ME | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110605 | Caja Distribuidor Placa 4702-GKT ME | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110606 | Caja Distribuidor Placa 5260-PSF ME | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110607 | Caja Distribuidor Placa 2904-ILA ME | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110608 | Caja Distribuidor Placa 3872-XRI ME | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110609 | Caja Distribuidor Placa 1245-XLN ME | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110610 | Caja Distribuidor Placa 2725-PRC ME | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110611 | Caja Distribuidor Placa 4474-CDE ME | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110612 | Caja Distribuidor Placa 5687-SPE ME | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110613 | Caja Distribuidor 10 ME | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110700 | CAJA CHICA | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1110701 | Caja chica Casa Matriz MN | UNRESOLVED | 1494 | 0.0 | 7000.0 | HR vocabulary without reliable account class |
| 1110702 | Caja chica 2do. Anillo MN | UNRESOLVED | 912 | 6206.58 | 15000.01 | HR vocabulary without reliable account class |
| 1110703 | Caja Chica Laboratorio MN | UNRESOLVED | 3044 | 3.14 | 15482.61 | HR vocabulary without reliable account class |
| 1110704 | Caja chica Saavedra MN | UNRESOLVED | 782 | -1919.0 | 81.0 | HR vocabulary without reliable account class |
| 1110705 | Caja chica La Paz MN | UNRESOLVED | 534 | 0.0 | 2000.0 | HR vocabulary without reliable account class |
| 1110706 | Caja chica Compras MN | UNRESOLVED | 22 | 6659.0 | 14059.0 | HR vocabulary without reliable account class |
| 1110707 | Caja Chica Farmacia MN | UNRESOLVED | 21 | 1000.0 | 1000.0 | HR vocabulary without reliable account class |
| 1120503 | Anticipo a cuenta de utilidades MN | EMPLOYEE_ADVANCE | 73 | 800000.0 | 5393500.0 | asset account + employee advance vocabulary |
| 1120700 | PRESTAMOS A TERCEROS MONEDA NACIONAL | EMPLOYEE_ADVANCE | 0 | 0.0 | 0.0 | asset account + employee advance vocabulary |
| 1120701 | Prestamos al Personal MN | EMPLOYEE_ADVANCE | 1150 | -21820.61 | 111904.88 | asset account + employee advance vocabulary |
| 1120800 | PRESTAMOS A TERCEROS MONEDA EXTRANJERA | EMPLOYEE_ADVANCE | 0 | 0.0 | 0.0 | asset account + employee advance vocabulary |
| 1121000 | ANTICIPOS AL PERSONAL | EMPLOYEE_ADVANCE | 0 | 0.0 | 0.0 | asset account + employee advance vocabulary |
| 1121001 | Anticipos al personal | EMPLOYEE_ADVANCE | 12611 | -12302.26 | 6670.52 | asset account + employee advance vocabulary |
| 1121002 | Anticipo de sueldos | EMPLOYEE_ADVANCE | 498 | -188894.24 | -2201335.42 | asset account + employee advance vocabulary |
| 1121300 | ANTICIPO PROVEEDORES MONEDA NACIONAL | EMPLOYEE_ADVANCE | 0 | 0.0 | 0.0 | asset account + employee advance vocabulary |
| 1121301 | Anticipo proveedores MN | EMPLOYEE_ADVANCE | 155023 | 528363.17 | 1325680.79 | asset account + employee advance vocabulary |
| 1121302 | Anticipo prov MN | EMPLOYEE_ADVANCE | 1 | 0.0 | 20079.0 | asset account + employee advance vocabulary |
| 1121400 | ANTICIPO PROVEEDORES MONEDA EXTRANJERA | EMPLOYEE_ADVANCE | 0 | 0.0 | 0.0 | asset account + employee advance vocabulary |
| 1121401 | Anticipo proveedores ME | EMPLOYEE_ADVANCE | 697 | 588902.95 | 591839.6 | asset account + employee advance vocabulary |
| 1121402 | Anticipo Importaciones ME | EMPLOYEE_ADVANCE | 0 | 0.0 | 0.0 | asset account + employee advance vocabulary |
| 1130101 | Almacén Materia Prima | UNRESOLVED | 22371 | -643819.53 | 7767560.53 | HR vocabulary without reliable account class |
| 1130103 | Almacen Ventas Materia Prima LAB | UNRESOLVED | 7 | 0.0 | 197784.33 | HR vocabulary without reliable account class |
| 1130205 | Almacén Retención | UNRESOLVED | 2993 | 15513.08 | 107252.75 | HR vocabulary without reliable account class |
| 1130314 | Almacen Movil  4702 GIP | UNRESOLVED | 22937 | 4247.56 | 7960.46 | HR vocabulary without reliable account class |
| 1130315 | Almacen Movil 4702 GKT | UNRESOLVED | 24029 | 6.57 | 132.99 | HR vocabulary without reliable account class |
| 1130316 | Almacen Movil  5260 PSF | UNRESOLVED | 19786 | 3704.39 | 3704.39 | HR vocabulary without reliable account class |
| 1130317 | Almacen Movil Ruta 2904 ILA | UNRESOLVED | 9346 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1130318 | Almacen Movil Ruta 5260 IHY | UNRESOLVED | 8417 | 581.23 | 835.94 | HR vocabulary without reliable account class |
| 1130319 | Almacen Movil Provincia 3872 XRI | UNRESOLVED | 7794 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1130320 | Almacen Movil Provincia 1245 XLN | UNRESOLVED | 8117 | 146.69 | 146.69 | HR vocabulary without reliable account class |
| 1130321 | Almacen Movil 5687 SPE | UNRESOLVED | 8028 | 4699.45 | 4699.45 | HR vocabulary without reliable account class |
| 1130322 | Almacen Movil 4438 ZHG | UNRESOLVED | 6372 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1130334 | Almacen Movil 5592-EBI | UNRESOLVED | 26342 | 138.25 | 138.25 | HR vocabulary without reliable account class |
| 1130344 | Almacen Movil 2725 PRC | UNRESOLVED | 16679 | 3005.69 | 3005.69 | HR vocabulary without reliable account class |
| 1130358 | Almacen Movil 600-KCI | UNRESOLVED | 6148 | 2178.18 | 3313.23 | HR vocabulary without reliable account class |
| 1130359 | Almacen Movil Eventos | UNRESOLVED | 7 | 1.72 | 1.72 | HR vocabulary without reliable account class |
| 1130366 | Almacen  Móvil 5268 FRR | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1240200 | RETENCION JUDICIAL | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 1240201 | Retencion Judicial | UNRESOLVED | 41 | -469.0 | 9684.0 | HR vocabulary without reliable account class |
| 2110102 | Caja chica por Pagar MN | OTHER_HR_LIABILITY | 95 | 0.0 | 0.0 | liability account + HR vocabulary |
| 2120000 | OBLIGACIONES AL PERSONAL | OTHER_HR_LIABILITY | 0 | 0.0 | 0.0 | liability account + HR vocabulary |
| 2120101 | Sueldos por pagar | SALARIES_PAYABLE | 972 | -6379.96 | -6379.96 | liability account + salary vocabulary |
| 2120102 | Subsidios por pagar | OTHER_HR_LIABILITY | 125 | 0.0 | 0.0 | liability account + HR vocabulary |
| 2120103 | Beneficios por Pagar | BENEFITS_PAYABLE | 0 | 0.0 | 0.0 | liability account + benefit vocabulary |
| 2120104 | Comisiones por pagar | OTHER_HR_LIABILITY | 848 | -67593.24 | -67593.24 | liability account + HR vocabulary |
| 2120105 | Aguinaldos por pagar | BENEFITS_PAYABLE | 169 | 0.0 | 0.0 | liability account + benefit vocabulary |
| 2120106 | Primas por pagar | OTHER_HR_LIABILITY | 0 | 0.0 | 0.0 | liability account + HR vocabulary |
| 2120107 | Subsidio por pagar al personal | OTHER_HR_LIABILITY | 55 | 38000.0 | 20000.0 | liability account + HR vocabulary |
| 2120108 | Sueldo interno por pagar | SALARIES_PAYABLE | 140 | 0.0 | 0.0 | liability account + salary vocabulary |
| 2120110 | Personal Eventual por pagar | OTHER_HR_LIABILITY | 73 | 0.0 | 0.0 | liability account + HR vocabulary |
| 2120111 | Bono Antiguedad por pagar | BENEFITS_PAYABLE | 2 | 0.0 | 0.0 | liability account + benefit vocabulary |
| 2120114 | Vacaciones por pagar | VACATION_PROVISION | 4 | 0.0 | 0.0 | liability account + vacation vocabulary |
| 2120115 | Bono de Transporte por pagar | BENEFITS_PAYABLE | 8 | 0.0 | 0.0 | liability account + benefit vocabulary |
| 2120116 | Sueldo por pagar Socio | SALARIES_PAYABLE | 19 | 0.0 | 0.0 | liability account + salary vocabulary |
| 2120200 | APORTES PATRONALES | CONTRIBUTIONS_PAYABLE | 0 | 0.0 | 0.0 | liability account + social contribution vocabulary |
| 2120201 | Caja Nacional de Salud | CONTRIBUTIONS_PAYABLE | 547 | 4480.69 | -86414.63 | liability account + social contribution vocabulary |
| 2120202 | AFP Futuro | CONTRIBUTIONS_PAYABLE | 138 | 0.0 | 0.0 | liability account + social contribution vocabulary |
| 2120203 | AFP Previsión | CONTRIBUTIONS_PAYABLE | 127 | 0.0 | 0.0 | liability account + social contribution vocabulary |
| 2120204 | Aporte Provivienda | CONTRIBUTIONS_PAYABLE | 0 | 0.0 | 0.0 | liability account + social contribution vocabulary |
| 2120205 | Gestora Publica | CONTRIBUTIONS_PAYABLE | 764 | -28994.83 | -176604.0 | liability account + social contribution vocabulary |
| 2120301 | Provisiones para aguinaldo | BENEFITS_PAYABLE | 679 | -612811.49 | -612811.49 | liability account + benefit vocabulary |
| 2120304 | Honorarios profesionales por pagar | OTHER_HR_LIABILITY | 28 | 0.0 | 0.0 | liability account + HR vocabulary |
| 2120305 | Provision Vacaciones por pagar | VACATION_PROVISION | 49 | -54784.45 | -54784.45 | liability account + vacation vocabulary |
| 2120400 | DESCUENTOS AL PERSONAL | OTHER_HR_LIABILITY | 0 | 0.0 | 0.0 | liability account + HR vocabulary |
| 2120401 | Atrasos del  personal | OTHER_HR_LIABILITY | 900 | 0.0 | 0.0 | liability account + HR vocabulary |
| 2120402 | Faltas del  personal | OTHER_HR_LIABILITY | 118 | 0.0 | 0.0 | liability account + HR vocabulary |
| 2120403 | Descuentos Varios al personal | OTHER_HR_LIABILITY | 108 | -47256.54 | -47256.54 | liability account + HR vocabulary |
| 3110200 | APORTES POR CAPITALIZAR | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 3110201 | Aportes por capitalizar | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 4210113 | Atrasos del personal | UNRESOLVED | 4 | 0.0 | 785.0 | HR vocabulary without reliable account class |
| 4210114 | Permisos al personal | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 4210115 | Faltas del personal | UNRESOLVED | 8 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 6010100 | GASTOS DE PERSONAL | SALARY_EXPENSE | 0 | 0.0 | 0.0 | expense account + salary/personnel vocabulary or payroll code |
| 6010101 | Haber basico | SALARY_EXPENSE | 896 | 5250757.68 | 5250757.68 | expense account + salary/personnel vocabulary or payroll code |
| 6010102 | Haber basico I | SALARY_EXPENSE | 329 | 979426.13 | 979426.13 | expense account + salary/personnel vocabulary or payroll code |
| 6010103 | Provisión Incremento Salarial | SALARY_EXPENSE | 0 | 0.0 | 0.0 | expense account + salary/personnel vocabulary or payroll code |
| 6010104 | Prestacion de Servicios | SALARY_EXPENSE | 166 | 566951.94 | 566951.94 | expense account + salary/personnel vocabulary or payroll code |
| 6010105 | Bono de Antigüedad | BONUS_EXPENSE | 639 | 761514.6 | 761514.6 | expense account + bonus/aguinaldo vocabulary |
| 6010106 | Otros bonos | BONUS_EXPENSE | 414 | 343597.16 | 343597.16 | expense account + bonus/aguinaldo vocabulary |
| 6010107 | Aguinaldo | BONUS_EXPENSE | 945 | 593093.04 | 593093.04 | expense account + bonus/aguinaldo vocabulary |
| 6010108 | Bono primas | BONUS_EXPENSE | 0 | 0.0 | 0.0 | expense account + bonus/aguinaldo vocabulary |
| 6010109 | CNS | EMPLOYER_CONTRIBUTIONS | 897 | 607790.01 | 607790.01 | expense account + social contribution vocabulary |
| 6010110 | Gestora Publica | EMPLOYER_CONTRIBUTIONS | 934 | 470194.55 | 470194.55 | expense account + social contribution vocabulary |
| 6010111 | Comisión sobre ventas | SALES_COMMISSION | 124 | 535904.84 | 535904.84 | expense account + sales/delivery commission vocabulary |
| 6010112 | Incentivos al personal | SALARY_EXPENSE | 134 | 19767.01 | 19767.01 | expense account + salary/personnel vocabulary or payroll code |
| 6010113 | Horas Extras | SALARY_EXPENSE | 21 | 52473.77 | 52473.77 | expense account + salary/personnel vocabulary or payroll code |
| 6010114 | Personal eventual | SALARY_EXPENSE | 79 | 466205.91 | 466205.91 | expense account + salary/personnel vocabulary or payroll code |
| 6010115 | Vacaciones | VACATION_EXPENSE | 265 | 107831.22 | 107831.22 | expense account + vacation vocabulary |
| 6010116 | Indemnizaciones laborales | SEVERANCE_EXPENSE | 945 | 593093.04 | 593093.04 | expense account + severance vocabulary |
| 6010117 | Bonos Ventas | BONUS_EXPENSE | 164 | 36874.56 | 36874.56 | expense account + bonus/aguinaldo vocabulary |
| 6010118 | Gratificaciones al personal | SALARY_EXPENSE | 21 | 120138.67 | 120138.67 | expense account + salary/personnel vocabulary or payroll code |
| 6010119 | Comisiones por negociacion | SALARY_EXPENSE | 12 | 0.0 | 0.0 | expense account + salary/personnel vocabulary or payroll code |
| 6010200 | OTROS GASTOS DEL PERSONAL | SALARY_EXPENSE | 0 | 0.0 | 0.0 | expense account + salary/personnel vocabulary or payroll code |
| 6010201 | Ropa de Trabajo FFVV | SALARY_EXPENSE | 17 | 5968.2 | 5968.2 | expense account + salary/personnel vocabulary or payroll code |
| 6010202 | Capacitacion del personal | SALARY_EXPENSE | 21 | 54027.4 | 54027.4 | expense account + salary/personnel vocabulary or payroll code |
| 6010203 | Gastos medicos | SALARY_EXPENSE | 11 | 3868.95 | 3868.95 | expense account + salary/personnel vocabulary or payroll code |
| 6010204 | Programas de Pasantias | SALARY_EXPENSE | 61 | 44879.99 | 44879.99 | expense account + salary/personnel vocabulary or payroll code |
| 6010205 | Materiales, suministros de seguridad y EPP | SALARY_EXPENSE | 43 | 22958.01 | 22958.01 | expense account + salary/personnel vocabulary or payroll code |
| 6010206 | EPP's y ropa de trabajo operaciones | SALARY_EXPENSE | 42 | 66158.67 | 66158.67 | expense account + salary/personnel vocabulary or payroll code |
| 6010207 | Subsidios | SALARY_EXPENSE | 48 | 130320.0 | 130320.0 | expense account + salary/personnel vocabulary or payroll code |
| 6010208 | Alimentacion del personal | SALARY_EXPENSE | 274 | 309365.01 | 309365.01 | expense account + salary/personnel vocabulary or payroll code |
| 6010209 | Bienestar Laboral | SALARY_EXPENSE | 84 | 37422.48 | 37422.48 | expense account + salary/personnel vocabulary or payroll code |
| 6010404 | Viaticos (alimentacion y transporte) | OTHER_PERSONNEL_EXPENSE | 95 | 7286.67 | 7286.67 | expense account + personnel benefit vocabulary |
| 6010500 | HONORARIOS PROFESIONALES | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 6010501 | Honorarios Profesionales | UNRESOLVED | 130 | 297984.2 | 297984.2 | HR vocabulary without reliable account class |
| 6010806 | Telefonia Movil | UNRESOLVED | 497 | 118051.78 | 118051.78 | HR vocabulary without reliable account class |
| 6011510 | Comision delivery | SALES_COMMISSION | 62 | 19435.17 | 19435.17 | expense account + sales/delivery commission vocabulary |
| 6011512 | Bono de Transporte | BONUS_EXPENSE | 69 | 32625.31 | 32625.31 | expense account + bonus/aguinaldo vocabulary |
| 6011708 | Comision por negociaciones | UNRESOLVED | 8 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 6020103 | Comisión tarjetas debito/credito | UNRESOLVED | 192 | 38819.7 | 38819.7 | HR vocabulary without reliable account class |
| 6020104 | Comision Bancaria | UNRESOLVED | 100 | 4978.89 | 4978.89 | HR vocabulary without reliable account class |
| 6020105 | Comision Bancaria por giros al exterior | UNRESOLVED | 109 | 1090697.04 | 1090697.04 | HR vocabulary without reliable account class |
| 6020200 | SOCIOS | SALARY_EXPENSE | 0 | 0.0 | 0.0 | expense account + salary/personnel vocabulary or payroll code |
| 6020201 | Haber básico - Socios | SALARY_EXPENSE | 22 | 0.0 | 0.0 | expense account + salary/personnel vocabulary or payroll code |
| 6020202 | Haber básico interno - Socios | SALARY_EXPENSE | 124 | 736000.0 | 736000.0 | expense account + salary/personnel vocabulary or payroll code |
| 6020203 | Bono de Antigüedad - Socios | BONUS_EXPENSE | 21 | 0.0 | 0.0 | expense account + bonus/aguinaldo vocabulary |
| 6020204 | CNS - Socios | EMPLOYER_CONTRIBUTIONS | 79 | 18190.56 | 18190.56 | expense account + social contribution vocabulary |
| 6020205 | Gestora Pública - Socios | EMPLOYER_CONTRIBUTIONS | 81 | 13114.6 | 13114.6 | expense account + social contribution vocabulary |
| 6020206 | Bono Becas de Estudio - Socios | BONUS_EXPENSE | 78 | 245104.57 | 245104.57 | expense account + bonus/aguinaldo vocabulary |
| 6020207 | Gastos especiales - Socios | SALARY_EXPENSE | 20 | 79963.0 | 79963.0 | expense account + salary/personnel vocabulary or payroll code |
| 6020208 | Seguros medicos - Socios | SALARY_EXPENSE | 24 | 54243.18 | 54243.18 | expense account + salary/personnel vocabulary or payroll code |
| 6020209 | Gastos extraordinarios - Socios | SALARY_EXPENSE | 0 | 0.0 | 0.0 | expense account + salary/personnel vocabulary or payroll code |
| 6020210 | Comisiones por negociación con proveedores - Socios | SALARY_EXPENSE | 10 | 0.0 | 0.0 | expense account + salary/personnel vocabulary or payroll code |
| 6020211 | Aguinaldo - Socios | BONUS_EXPENSE | 84 | 61321.3 | 61321.3 | expense account + bonus/aguinaldo vocabulary |
| 6020212 | Indemnizaciones laborales - Socios | SEVERANCE_EXPENSE | 84 | 61321.3 | 61321.3 | expense account + severance vocabulary |
| 6020213 | Prestacion de servicios - Socios | SALARY_EXPENSE | 16 | 91122.75 | 91122.75 | expense account + salary/personnel vocabulary or payroll code |
| 610124 | Prestacion de servicios NO UTILIZAR | SALARY_EXPENSE | 10 | 0.0 | 0.0 | expense account + salary/personnel vocabulary or payroll code |
| 610125 | Accionistas - Sueldos NO UTILIZAR | SALARY_EXPENSE | 2 | 0.0 | 0.0 | expense account + salary/personnel vocabulary or payroll code |
| 6110100 | GASTOS DE PERSONAL | SALARY_EXPENSE | 0 | 0.0 | 0.0 | expense account + salary/personnel vocabulary or payroll code |
| 6110101 | Sueldos y salarios | SALARY_EXPENSE | 1498 | 0.0 | 31964687.89 | expense account + salary/personnel vocabulary or payroll code |
| 6110102 | Cargas Sociales | EMPLOYER_CONTRIBUTIONS | 692 | 0.0 | 4922780.12 | expense account + social contribution vocabulary |
| 6110103 | Beneficios sociales | EMPLOYER_CONTRIBUTIONS | 39 | 0.0 | 6136.74 | expense account + social contribution vocabulary |
| 6110104 | Seguros medico socios | SALARY_EXPENSE | 44 | 0.0 | 639009.01 | expense account + salary/personnel vocabulary or payroll code |
| 6110105 | Capacitación del personal | SALARY_EXPENSE | 154 | 0.0 | 204554.52 | expense account + salary/personnel vocabulary or payroll code |
| 6110106 | Refrigerios | SALARY_EXPENSE | 2666 | 0.0 | 361417.84 | expense account + salary/personnel vocabulary or payroll code |
| 6110107 | Horas extras | SALARY_EXPENSE | 280 | 0.0 | 111269.58 | expense account + salary/personnel vocabulary or payroll code |
| 6110108 | Ropa de trabajo y de bioseguridad | SALARY_EXPENSE | 286 | 0.0 | 260085.34 | expense account + salary/personnel vocabulary or payroll code |
| 6110109 | Subsidio de natalidad | SALARY_EXPENSE | 40 | 0.0 | 64000.0 | expense account + salary/personnel vocabulary or payroll code |
| 6110110 | Subsidio prenatal | SALARY_EXPENSE | 158 | 0.0 | 287870.4 | expense account + salary/personnel vocabulary or payroll code |
| 6110111 | Subsidio de lactancia | SALARY_EXPENSE | 273 | 0.0 | 588460.0 | expense account + salary/personnel vocabulary or payroll code |
| 6110112 | Vacaciones | VACATION_EXPENSE | 270 | 0.0 | 428094.06 | expense account + vacation vocabulary |
| 6110113 | Bono Antiguedad | BONUS_EXPENSE | 587 | 0.0 | 2856621.78 | expense account + bonus/aguinaldo vocabulary |
| 6110114 | Bonos Ventas | BONUS_EXPENSE | 163 | 0.0 | 242899.4 | expense account + bonus/aguinaldo vocabulary |
| 6110115 | Otros Bonos | BONUS_EXPENSE | 376 | 0.0 | 2449954.74 | expense account + bonus/aguinaldo vocabulary |
| 6110116 | Aguinaldo | BONUS_EXPENSE | 713 | 0.0 | 2151390.73 | expense account + bonus/aguinaldo vocabulary |
| 6110117 | Indemnizacion | SEVERANCE_EXPENSE | 686 | 0.0 | 2943440.86 | expense account + severance vocabulary |
| 6110118 | Gastos especiales | SALARY_EXPENSE | 230 | 0.0 | 959401.54 | expense account + salary/personnel vocabulary or payroll code |
| 6110119 | Deshaucio | SALARY_EXPENSE | 42 | 0.0 | 310913.69 | expense account + salary/personnel vocabulary or payroll code |
| 6110120 | Incentivos al Personal | SALARY_EXPENSE | 413 | 0.0 | 96614.33 | expense account + salary/personnel vocabulary or payroll code |
| 6110121 | Primas | SALARY_EXPENSE | 3 | 0.0 | 70950.0 | expense account + salary/personnel vocabulary or payroll code |
| 6110122 | Personal Eventual | SALARY_EXPENSE | 351 | 0.0 | 459824.48 | expense account + salary/personnel vocabulary or payroll code |
| 6110123 | Pasantía | SALARY_EXPENSE | 78 | 0.0 | 63093.33 | expense account + salary/personnel vocabulary or payroll code |
| 6110124 | Prestacion de Servicio - Sueldo | SALARY_EXPENSE | 52 | 0.0 | 910918.35 | expense account + salary/personnel vocabulary or payroll code |
| 6110125 | Accionistas - Sueldo | SALARY_EXPENSE | 97 | 0.0 | 0.0 | expense account + salary/personnel vocabulary or payroll code |
| 6110200 | OTROS GASTOS DE PERSONAL | SALARY_EXPENSE | 0 | 0.0 | 0.0 | expense account + salary/personnel vocabulary or payroll code |
| 6110201 | Gastos de viaje, pasajes | SALARY_EXPENSE | 225 | 0.0 | 168739.65 | expense account + salary/personnel vocabulary or payroll code |
| 6110202 | Viáticos | SALARY_EXPENSE | 852 | 0.0 | 267048.23 | expense account + salary/personnel vocabulary or payroll code |
| 6110203 | Otros gastos de personal | SALARY_EXPENSE | 12 | 0.0 | 3613.07 | expense account + salary/personnel vocabulary or payroll code |
| 6110204 | Hospedaje | SALARY_EXPENSE | 396 | 0.0 | 85837.28 | expense account + salary/personnel vocabulary or payroll code |
| 6210103 | Comisiones sobre ventas | SALES_COMMISSION | 987 | 0.0 | 3116438.69 | expense account + sales/delivery commission vocabulary |
| 6210104 | Comision delivery | SALES_COMMISSION | 316 | 0.0 | 50459.0 | expense account + sales/delivery commission vocabulary |
| 6210105 | Comision tarjetas debito/credito | UNRESOLVED | 1206 | 0.0 | 302468.63 | HR vocabulary without reliable account class |
| 6210112 | Bonificaciones y promociones | BONUS_EXPENSE | 721 | 0.0 | 142569.56 | expense account + bonus/aguinaldo vocabulary |
| 6210114 | Comisiones Seguro Alianza | UNRESOLVED | 0 | 0.0 | 0.0 | HR vocabulary without reliable account class |
| 6410102 | Comisiones bancarias | UNRESOLVED | 951 | 0.0 | 215231.61 | HR vocabulary without reliable account class |
| 6410104 | Comision Bancaria Giros | UNRESOLVED | 337 | 0.0 | 6868368.56 | HR vocabulary without reliable account class |
| 6610102 | Transportes al personal | SALARY_EXPENSE | 3266 | 0.0 | 295375.13 | expense account + salary/personnel vocabulary or payroll code |
| 6610120 | Honorarios profesionales | UNRESOLVED | 854 | 0.0 | 2205620.66 | HR vocabulary without reliable account class |
| 6610123 | Gastos medicos y medicamentos | OTHER_PERSONNEL_EXPENSE | 263 | 0.0 | 110413.61 | expense account + personnel benefit vocabulary |
| 6610125 | Alimentacion al personal | SALARY_EXPENSE | 1790 | 0.0 | 1238279.95 | expense account + salary/personnel vocabulary or payroll code |
| 6610138 | Materiales y suministros de seguridad EPP | OTHER_PERSONNEL_EXPENSE | 320 | 0.0 | 190313.64 | expense account + personnel benefit vocabulary |
| 6610151 | Bienestar Laboral | OTHER_PERSONNEL_EXPENSE | 48 | 0.0 | 59213.32 | expense account + personnel benefit vocabulary |
| 6710103 | Haber Basico Interno - Socios | SALARY_EXPENSE | 22 | 0.0 | 974000.0 | expense account + salary/personnel vocabulary or payroll code |
| 6710104 | Prestacion de Servicios - Socios | SALARY_EXPENSE | 4 | 0.0 | 0.0 | expense account + salary/personnel vocabulary or payroll code |
| 6710105 | Bono Antiguedad - Socios | BONUS_EXPENSE | 0 | 0.0 | 0.0 | expense account + bonus/aguinaldo vocabulary |
| 6710106 | CNS - Socios | EMPLOYER_CONTRIBUTIONS | 39 | 0.0 | 24312.74 | expense account + social contribution vocabulary |
| 6710107 | Gestora - Socios | EMPLOYER_CONTRIBUTIONS | 20 | 0.0 | 50483.76 | expense account + social contribution vocabulary |
| 6710108 | Aguinaldo - Socios | BONUS_EXPENSE | 22 | 0.0 | 21111.0 | expense account + bonus/aguinaldo vocabulary |
| 6710109 | Indemnizaciones Laborales - Socios | SEVERANCE_EXPENSE | 22 | 0.0 | 21111.0 | expense account + severance vocabulary |

## H. GASTO LABORAL

Suma YTD de cuentas clasificadas como gasto HR: **13600311.25**. El P&L vigente se usa como control; el detalle mensual y categorías están en JSON.

## I. SUELDOS

Las cuentas de salario base y haber básico están separadas de bonos, cargas, vacaciones e indemnizaciones. El detalle por cuenta y período está en `accounts` y `hr_cost_periods`.

## J. CARGAS SOCIALES

CNS, Gestora y cargas sociales se clasifican como gasto patronal; sus pasivos se mantienen separados en `CONTRIBUTIONS_PAYABLE`.

## K. BONOS / AGUINALDO

Bonos, aguinaldo e incentivos tienen cuentas separadas cuando el nombre/código lo demuestra.

## L. VACACIONES / BENEFICIOS

Vacaciones e indemnizaciones se mantienen separadas de beneficios sociales; no se afirma provisión si no existe cuenta de pasivo/movimiento.

## M. COMISIONES

Solo comisiones de ventas/delivery se clasifican como `SALES_COMMISSION`; comisiones bancarias quedan fuera del costo laboral.

La serie comparativa 2026 YTD / 2025 mismo período / 2025 completo / últimos 12 meses está en `hr_cost_periods`.

## N. ANTICIPOS / PRÉSTAMOS EMPLEADOS

Las cuentas de activo candidatas quedan en `EMPLOYEE_ADVANCE`; el saldo GL no se convierte en préstamo individual sin vínculo empleado.

## O. PASIVOS LABORALES

Las cuentas de pasivo se agregan en `hr_liabilities`; los saldos persistentes se marcan REVIEW, no irregularidad.

## P. PAYROLL→GL

El GL se traza por JDT1→OJDT→OACT. La ausencia de payroll detallado no impide demostrar el costo contable que llega al P&L.

## Q. PAYROLL→PAYMENT→BANK

OVPM se inventaría y se busca TransType 46 sobre cuentas HR. No se observó vínculo BP empleado; un pago agregado no prueba pago empleado-por-empleado.

## R. HR CASH FLOW

El mecanismo de salida se conserva en `payment`; no se duplica cash-out fuera de Treasury.

## S. HEADCOUNT

Headcount mensual: 13 puntos desde OHEM; el mes vigente respeta Active/status y los meses históricos usan fechas, porque OHEM no conserva historia de Active.

## T. ALTAS / BAJAS

StartDate/termDate quedan disponibles para altas/bajas; no hay bajas demostrables cuando termDate es nulo.

## U. HR COST PER EMPLOYEE

No se declara salario promedio; el indicador contable queda `DEGRADED_UNTIL_EXPENSE_TO_HEADCOUNT_COMPARABILITY_PROVEN` hasta comparar costo GL y headcount bajo una definición de período común.

## V. HR COST / REVENUE

No se fuerza el ratio hasta cerrar la comparabilidad con revenue y payroll externo; ambos controles están en `pnl_control`.

## W. HR COST / OPEX

El HR expense YTD es subconjunto del OPEX cerrado; HR06 conserva el control numérico.

## X. COSTO POR ÁREA

Se preserva dept/CostCenter OHEM y ProfitCode GL; no se distribuye costo central sin dimensión.

## Y. COSTO POR SUCURSAL

BPLId GL tiene cobertura 0% en el universo HR YTD observado; no se asigna por heurística.

## Z. ASIENTOS MANUALES

TransType=30 y sus usuarios/montos se conservan en `gl.manual`; DataSource/UserSign no se sobreinterpreta como intención humana.

## AA. PROVISIONES / REVERSAS

AutoStorno, memo y patrón mensual se conservan en `gl.memo_patterns`; provisiones y reversas no se duplican en el gasto económico.

## AB. CUENTAS CON SALDOS PERSISTENTES

Revisión a nivel de cuenta, sin afirmar vencimiento cuando GL no provee DueDate laboral confiable.

## AC. CASOS REALES

Se preservan casos de GL con TransId, RefDate, TransType, cuenta, contraparte, memo y clasificación. Los casos de empleado solo usan IDs/coberturas y no exponen documentos, domicilios, teléfonos ni cuentas bancarias.

## AD. INVARIANTES

| Invariante | Resultado |
|---|---|
| HR01_employee_source_ohem | PASS |
| HR02_state_rule_reproducible | PASS |
| HR03_ohem_ousr_quantified | PASS |
| HR04_ohem_oslp_quantified | PASS |
| HR05_hr_accounts_exist_in_oact | PASS |
| HR06_expense_subset_pnl | PASS |
| HR07_liabilities_from_oact_gl | PASS |
| HR08_cash_mechanism_quantified | PASS |
| HR09_expense_separate_liability | PASS |
| HR10_liability_separate_payment | PASS |
| HR11_reversals_not_double_counted | PASS |
| HR12_cost_center_coverage_measured | PASS |
| HR13_no_detailed_payroll_claim_without_evidence | PASS |
| HR14_sensitive_personal_data_minimized | PASS |
| HR15_sap_write_count | PASS |

## AE. LIMITACIONES

- SAP contiene OHEM y GL; la presencia/ausencia de objetos candidatos no demuestra por sí sola que una nómina externa sea un software específico.
- No se exponen datos personales innecesarios.
- El costo contable no equivale a salario promedio.
- La asignación por branch/cost center solo es confiable donde OHEM/JDT1 la conserva.

## AF. CONTROLES FUTUROS

Employee master vs payroll, payroll vs GL, payroll vs bank, terminados con pagos, anticipos abiertos, pasivos aged y missing cost center.

## AG. PRÓXIMO GATE

`TELCHI_EXTERNAL_PAYROLL_TO_SAP_RECONCILIATION_V1` si el payroll se confirma externo; de lo contrario `TELCHI_HR_COST_HEADCOUNT_PRODUCTIVITY_V1`.

## Artefactos

- JSON: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/hr_payroll_accounting_traceability/hr_payroll_accounting_traceability_v1.json`
- Runner: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/hr_payroll_accounting_traceability/hr_payroll_accounting_traceability_v1.py`
- Fuente: SAP HANA `TELCHI`, SELECT-only.
