"""TELCHI — Comercial Opportunities → Proforma → Stock → Precio → Venta Real.

Capa de trazabilidad ejecutiva sobre fuentes comerciales (Excel) y SAP HANA
(READ ONLY). Nunca modifica SAP, nunca escribe en HANA, nunca altera los Excel
fuente. Los Excel son INPUT de hipótesis/declaración comercial; SAP y las
fuentes operativas validan o refutan la declaración.
"""