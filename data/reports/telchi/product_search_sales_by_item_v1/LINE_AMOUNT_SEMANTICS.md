# Line amount semantics

Foundation `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot **1408**, CURRENT efectivo confirmado; solo DEV y lectura. Sin SAP, modificaciones canónicas, reingestión, deploy ni cambio de modelo.

Estado **PARTIAL**: importes de producto no acreditados. LineTotal existe en Atomic, pero impuestos, descuentos de cabecera, moneda/signo y asignación de NC no tienen aquí contrato neto aprobado por producto. El servicio no expone LineTotal como importe acreditado y nunca asigna DocTotal a cada línea.

DocTotal mensual de cabecera se conserva sin cambio: mayo neto Bs 8.552.079,19; junio Bs 9.763.493,67, derivados de Foundation. Estos valores son controles de regresión, no respuestas hardcodeadas.

Quantity existe por línea. UoM/factor físico de línea no está publicado en sales_line; sales_uom_id de catálogo no acredita esa unidad. Se entregan cantidades documentales originales sin totalizar cantidades físicas, con explicación explícita. Solicitudes de importes/cantidades reciben la parte verificable, no una negativa total.

Para ventas netas por producto se necesita un contrato de línea y NC separado; no se promueve semántica por analogía con cabeceras.
