"""Native actual-production receipt projection (OIGN/IGN1), not OWOR output."""
from .material_supply_fact_capture import DatasetSpec, _f

SPEC = DatasetSpec(
    name='production_receipt', header_table='OIGN', line_table='IGN1', date_field='DocDate',
    key_fields=('DocEntry','LineNum'), quantity_field='Quantity',
    fields=tuple(_f(n,'H') for n in ('DocEntry','DocNum','DocDate','CANCELED','DocStatus')) +
           tuple(_f(n,'L') for n in ('LineNum','ItemCode','Quantity','WhsCode','BaseType','BaseEntry','BaseLine',
                                     'BaseRef','unitMsr','NumPerMsr','UomCode','U_LOTE')),
)
