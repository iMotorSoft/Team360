# Telchi

Telchi es un módulo de Team360 cuya implementación productiva se construirá progresivamente a partir de capacidades aprobadas.

## Estado actual

La carpeta `investigation/` conserva el reverse engineering de SAP, la semántica validada, los contratos, SQL, pruebas y gates de investigación. No es una API productiva y el módulo no registra rutas ni tareas de runtime.

## Frontera productiva

El código productivo futuro debe vivir fuera de `investigation/`. No debe importar directamente runners o artefactos de investigación: cada promoción requiere una implementación o refactor explícito con responsabilidad y consumidor productivos definidos.

## Datos y credenciales

El package no contiene secretos, Parquet, runtime ni evidencia pesada. Los datos físicos y secretos permanecen externos durante esta fase y se aislarán en gates dedicados.
