"""Reproducible, read-only inventory of validated Telchi SAP knowledge.

This runner scans the repository corpus and the external evidence manifest.  It
never imports a SAP connector and never writes outside the requested local
inventory/report outputs.  The curated catalogs deliberately preserve
confidence and gaps instead of turning SAP-standard joins into Telchi facts.

Run from the Team360 repository root:

    cd SrvRestAstroLS_v1/backend && python3 -m modules.telchi.investigation.validation.sap_knowledge_inventory_v1.inventory

or execute this file directly with Python 3.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[7]
INVESTIGATION = ROOT / "SrvRestAstroLS_v1/backend/modules/telchi/investigation"
DOCS = INVESTIGATION / "docs"
VALIDATION = INVESTIGATION / "validation"
OUTPUT = VALIDATION / "sap_knowledge_inventory_v1"
REPORT = DOCS / "TELCHI_SAP_KNOWLEDGE_INVENTORY_V1.md"
EVIDENCE_ROOT = Path(
    "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/"
    "investigation-consolidation-v1"
)
HISTORICAL_REPORT = DOCS / "TELCHI_HISTORICAL_DATA_INVENTORY_V1.md"

GATE_RE = re.compile(
    r"\b(?:TELCHI|TEAM360_TELCHI)_[A-Z0-9_]+(?:_PASS|_DEGRADED|_FAIL|"
    r"_INCOMPLETE|_HISTORICAL|_UNKNOWN|_PARTIAL)\b"
)
STATUS_SUFFIXES = (
    "_DEGRADED",
    "_INCOMPLETE",
    "_HISTORICAL",
    "_UNKNOWN",
    "_PARTIAL",
    "_PASS",
    "_FAIL",
)

# This is intentionally a catalog, not a schema proposal.  Columns are the
# fields actually used in the cited investigations, not an exhaustive SAP
# dictionary.
TABLE_SPECS = [
    ("OITM", "PRODUCTOS", "item master and MRP/product attributes", "ItemCode", "ItemCode,ItemName,InvntItem,PrchseItem,LeadTime,PlaningSys,PrcrmntMtd,ReorderPnt,MinLevel,MaxLevel,OrdrMulti", "stock,production,mrp,seasonality,purchases", "OITW,ITT1,OWOR,OCRD", "CONFIRMED"),
    ("OITW", "STOCK_E_INVENTARIOS", "current item-by-warehouse position and policy", "ItemCode+WhsCode", "ItemCode,WhsCode,OnHand,IsCommited,OnOrder,MinStock,MaxStock,MinOrder", "stock,mrp,coverage", "OITM,OWHS,OINM", "CONFIRMED"),
    ("OWHS", "ALMACENES", "warehouse master", "WhsCode", "WhsCode,WhsName,Inactive", "stock,transfers,production", "OITW,WTR1,OINM", "CONFIRMED"),
    ("OITB", "PRODUCTOS", "item group used in product/business classification", "ItmsGrpCod", "ItmsGrpCod,ItmsGrpNam", "stock,La Reja,production", "OITM", "CONFIRMED"),
    ("OINV", "VENTAS", "sales invoice header", "DocEntry", "DocEntry,DocNum,CardCode,DocDate,DocDueDate,DocTotal,PaidToDate,CANCELED,UserSign,TransId,U_ORIGIN,U_SO1_01RETAILONE", "sales,credit,temporal,users,finance", "INV1,OCRD,ORCT,OINM,OJDT", "CONFIRMED"),
    ("INV1", "VENTAS", "sales invoice lines and document lineage", "DocEntry+LineNum", "DocEntry,LineNum,ItemCode,Quantity,Price,DiscPrcnt,BaseType,BaseEntry,BaseLine,WhsCode,GTotal", "sales,credit,proforma,delivery,temporal", "OINV,ODLN,ORDR,OQUT,OINM", "CONFIRMED"),
    ("INV6", "CRÉDITO_Y_DEUDORES", "invoice installment/due-date mirror", "DocEntry+InstlmntID", "DocEntry,InstlmntID,DueDate,InsTotal,Status", "credit,aging,temporal", "OINV,ITR1,OITR", "CONFIRMED"),
    ("ORIN", "NOTAS_DE_CREDITO", "credit note header", "DocEntry", "DocEntry,DocNum,CardCode,DocDate,DocTotal,CANCELED,TransId", "credit,financial,temporal", "RIN1,OINV,ITR1,OJDT", "CONFIRMED"),
    ("RIN1", "NOTAS_DE_CREDITO", "credit note lines and base document lineage", "DocEntry+LineNum", "DocEntry,LineNum,ItemCode,Quantity,BaseType,BaseEntry,BaseLine", "credit,temporal", "ORIN,OINV,INV1,OINM", "CONFIRMED"),
    ("ODLN", "VENTAS", "delivery header", "DocEntry", "DocEntry,CardCode,DocDate,DocTotal,CANCELED,UserSign", "delivery,credit,warehouse_exit", "DLN1,OCRD,OINM,INV1", "CONFIRMED"),
    ("DLN1", "VENTAS", "delivery lines", "DocEntry+LineNum", "DocEntry,LineNum,ItemCode,Quantity,WhsCode,BaseType,BaseEntry", "delivery,warehouse_exit", "ODLN,OINV,OINM", "CONFIRMED"),
    ("ORDR", "VENTAS", "sales order header", "DocEntry", "DocEntry,DocNum,CardCode,DocDate,DocStatus,CANCELED,UserSign", "credit,order_delivery", "RDR1,OINV,ODLN,OCRD", "CONFIRMED"),
    ("RDR1", "VENTAS", "sales order lines", "DocEntry+LineNum", "DocEntry,LineNum,ItemCode,Quantity,BaseType,BaseEntry,BaseLine", "credit,order_delivery", "ORDR,ODLN,OINV", "CONFIRMED"),
    ("OQUT", "COTIZACIONES_PROFORMAS", "quotation/proforma header", "DocEntry", "DocEntry,DocNum,CardCode,DocDate,DocTotal,CANCELED", "proforma,pricing", "QUT1,OCRD,INV1", "CONFIRMED"),
    ("QUT1", "COTIZACIONES_PROFORMAS", "quotation/proforma lines", "DocEntry+LineNum", "DocEntry,LineNum,ItemCode,Quantity,Price,DiscPrcnt,GTotal", "proforma,pricing", "OQUT,INV1", "CONFIRMED"),
    ("OCRD", "CLIENTES_PROVEEDORES", "business partner master for customers and suppliers", "CardCode", "CardCode,CardName,CardType,LicTradNum,CreditLine,Balance,GroupCode,Country,U_CATCLIENTE,U_CANAL_VENTAS,U_TIPOCLIENTE", "credit,customers,purchases,La_Reja", "OINV,ORIN,ORCT,OPOR,OPCH,OCRG,OCTG", "CONFIRMED"),
    ("OCRG", "CLIENTES_PROVEEDORES", "business partner group", "GroupCode", "GroupCode,GroupName", "customers,La_Reja", "OCRD", "CONFIRMED"),
    ("OCTG", "CRÉDITO_Y_DEUDORES", "payment terms/group", "GroupNum", "GroupNum,PymntGroup,ExtraDays", "credit,aging", "OCRD,OINV", "CONFIRMED"),
    ("OSLP", "VENDEDORES", "salesperson master", "SlpCode", "SlpCode,SlpName,Active", "sales,users,AR", "OINV,OCRD,OHEM", "CONFIRMED"),
    ("ORCT", "COBRANZAS", "incoming payment header", "DocEntry", "DocEntry,DocNum,CardCode,DocDate,DocTotal,Canceled,TransId", "credit,payments,treasury", "RCT2,ITR1,OJDT,OCRD", "CONFIRMED"),
    ("RCT2", "COBRANZAS", "incoming payment invoice references (not settlement authority)", "DocNum+InvType+DocEntry", "DocNum,InvType,DocEntry,SumApplied", "payments,credit", "ORCT,OINV,ITR1", "CONFIRMED"),
    ("OITR", "RECONCILIACIONES", "internal reconciliation header and as-of date", "ReconNum", "ReconNum,ReconDate,Canceled,Total", "credit,temporal,reconciliation", "ITR1,OINV,ORCT,ORIN", "CONFIRMED"),
    ("ITR1", "RECONCILIACIONES", "reconciliation members and settlement amounts", "ReconNum+LineSeq", "ReconNum,LineSeq,SrcObjTyp,SrcObjAbs,ReconSum", "credit,temporal,reconciliation", "OITR,OINV,ORCT,ORIN,OPCH,OVPM", "CONFIRMED"),
    ("OPOR", "COMPRAS_Y_ABASTECIMIENTO", "purchase order header", "DocEntry", "DocEntry,DocNum,CardCode,DocDate,DocDueDate,DocStatus,CANCELED,DocCur,U_TIPOCOMPRA", "purchases,lead_time,mrp", "POR1,OCRD", "CONFIRMED"),
    ("POR1", "COMPRAS_Y_ABASTECIMIENTO", "purchase order lines", "DocEntry+LineNum", "DocEntry,LineNum,ItemCode,Quantity,OpenQty,BaseType,BaseEntry,BaseRef,BaseDocNum", "purchases,lead_time,coverage", "OPOR,OPCH,OPDN,OITM", "CONFIRMED"),
    ("OPRQ", "SOLICITUDES_DE_COMPRA", "purchase request header", "DocEntry", "DocEntry,DocNum,DocDate,DocStatus,CANCELED", "purchases", "PRQ1,POR1", "CONFIRMED"),
    ("PRQ1", "SOLICITUDES_DE_COMPRA", "purchase request lines", "DocEntry+LineNum", "DocEntry,LineNum,ItemCode,Quantity,BaseType,BaseEntry", "purchases", "OPRQ,OPOR", "CONFIRMED"),
    ("OPCH", "FACTURAS_DE_PROVEEDOR", "AP/vendor invoice header", "DocEntry", "DocEntry,DocNum,CardCode,DocDate,DocDueDate,DocTotal,PaidToDate,DocStatus,CANCELED,TransId", "purchases,AP,finance,debt", "PCH1,OCRD,ITR1,OVPM,OJDT", "CONFIRMED"),
    ("PCH1", "FACTURAS_DE_PROVEEDOR", "AP/vendor invoice lines", "DocEntry+LineNum", "DocEntry,LineNum,ItemCode,Quantity,BaseType,BaseEntry,BaseLine", "purchases,AP,lead_time", "OPCH,OPOR,OPDN", "CONFIRMED"),
    ("OPDN", "RECEPCIONES", "goods receipt header", "DocEntry", "DocEntry,DocNum,CardCode,DocDate,CANCELED,TransId", "purchases,lead_time", "PDN1,OPCH,OPOR,OINM", "CONFIRMED"),
    ("PDN1", "RECEPCIONES", "goods receipt lines", "DocEntry+LineNum", "DocEntry,LineNum,ItemCode,Quantity,BaseType,BaseEntry,BaseLine", "purchases,lead_time", "OPDN,OPCH,OPOR,OINM", "CONFIRMED"),
    ("ORPD", "DEVOLUCIONES", "purchase return header", "DocEntry", "DocEntry,DocNum,CardCode,DocDate,CANCELED", "purchases", "RPD1,OPCH,OPDN,OCRD", "CONFIRMED"),
    ("RPD1", "DEVOLUCIONES", "purchase return lines", "DocEntry+LineNum", "DocEntry,LineNum,ItemCode,Quantity,BaseType,BaseEntry", "purchases", "ORPD,OPCH,OPDN", "CONFIRMED"),
    ("OITT", "BOM_PRODUCCIÓN", "current bill-of-material header", "Code", "Code,Quantity,Type,TreeType,IssueMthd", "production,bom,mrp", "ITT1,OITM,OWOR", "CONFIRMED"),
    ("ITT1", "BOM_PRODUCCIÓN", "current BOM components", "Father,Code", "Father,Code,Quantity,IssueMthd,Warehouse", "production,bom,mrp", "OITT,OITM", "CONFIRMED"),
    ("OWOR", "PRODUCCIÓN", "production order header", "DocEntry", "DocEntry,DocNum,ItemCode,PlannedQty,CmpltQty,Status,Type,PostDate,Warehouse", "production,reconciliation", "WOR1,IGE1,IGN1,OINM", "CONFIRMED"),
    ("WOR1", "PRODUCCIÓN", "historical order component snapshot", "DocEntry+LineNum", "DocEntry,LineNum,ItemCode,BaseQty,BaseQtyNum,BaseQtyDen,IssuedQty,IssueType", "production,bom,reconciliation", "OWOR,IGE1,ITT1", "CONFIRMED"),
    ("OIGE", "PRODUCCIÓN", "goods issue header", "DocEntry", "DocEntry,DocNum,DocDate,CANCELED,TransId", "production", "IGE1,OWOR,OINM", "CONFIRMED"),
    ("IGE1", "PRODUCCIÓN", "actual component issue lines", "DocEntry+LineNum", "DocEntry,LineNum,ItemCode,Quantity,BaseType,BaseEntry,BaseLine,BaseRef", "production,consumption", "OIGE,OWOR,WOR1,OINM", "CONFIRMED"),
    ("OIGN", "PRODUCCIÓN", "goods receipt/output header", "DocEntry", "DocEntry,DocNum,DocDate,CANCELED,TransId", "production", "IGN1,OWOR,OINM", "CONFIRMED"),
    ("IGN1", "PRODUCCIÓN", "actual finished-good output lines", "DocEntry+LineNum", "DocEntry,LineNum,ItemCode,Quantity,BaseType,BaseEntry,BaseRef", "production,output", "OIGN,OWOR,OINM", "CONFIRMED"),
    ("OINM", "MOVIMIENTOS_DE_INVENTARIO", "inventory movement ledger", "TransNum+TransSeq", "TransNum,TransSeq,TransType,BASE_REF,DocDate,ItemCode,Warehouse,InQty,OutQty,Price", "stock,production,transfers,traceability", "OINV,IGE1,IGN1,OWTR,WTR1,OITW", "CONFIRMED"),
    ("OWTR", "TRANSFERENCIAS_Y_DEPÓSITOS", "inventory transfer header", "DocEntry", "DocEntry,DocNum,DocDate,ToWhsCode,FromWhsCod,CANCELED,UserSign", "transfers,warehouse_exit", "WTR1,OINM,OWHS", "CONFIRMED"),
    ("WTR1", "TRANSFERENCIAS_Y_DEPÓSITOS", "inventory transfer lines", "DocEntry+LineNum", "DocEntry,LineNum,ItemCode,Quantity,FromWhsCod,WhsCode,BaseType,BaseRef,U_LOTE", "transfers,warehouse_exit", "OWTR,OINM,OWHS,IBT1", "CONFIRMED"),
    ("IBT1", "LOTES_SERIES", "batch transaction ledger", "ItemCode+BatchNum+BaseEntry+BaseLinNum", "ItemCode,BatchNum,Quantity,BaseType,BaseEntry,BaseLinNum", "transfers,production,batches", "WTR1,OBTN,IGN1", "CONFIRMED"),
    ("OBTN", "LOTES_SERIES", "batch master", "AbsEntry", "ItemCode,DistNumber,AbsEntry,InDate,ExpDate", "production,transfers", "IBT1,IGN1", "LIKELY"),
    ("OFCT", "FORECAST_Y_ESTACIONALIDAD", "forecast header", "AbsID", "AbsID,Name,Code,StartDate,EndDate", "mrp,forecast", "FCT1,OITM", "CONFIRMED"),
    ("FCT1", "FORECAST_Y_ESTACIONALIDAD", "forecast rows", "AbsID+LineId", "AbsID,LineId,ItemCode,WhsCode,Date,Quantity", "mrp,forecast", "OFCT,OITM,OITW", "CONFIRMED"),
    ("OUSR", "USUARIOS_ROLES_Y_PERMISOS", "SAP user master", "USERID", "USERID,USER_CODE,USER_NAME,Locked,superuser,lastLogin,updateDate", "users,authorizations,channel", "USR3,USR5,OHEM", "CONFIRMED"),
    ("USR3", "USUARIOS_ROLES_Y_PERMISOS", "direct user permissions", "USERID+PermId", "USERID,PermId,Permission", "users,authorizations", "OUSR,UGR1", "CONFIRMED"),
    ("UGR1", "USUARIOS_ROLES_Y_PERMISOS", "group permissions", "GroupId+PermId", "GroupId,PermId,Permission", "users,authorizations", "OUGR,OUSR", "CONFIRMED"),
    ("USR5", "ACTIVIDAD_DE_USUARIOS", "user activity/session log", "USERID+LineNum", "USERID,ClientIP,Action,Date,Time", "users,activity", "OUSR,OHEM", "CONFIRMED"),
    ("OUGR", "USUARIOS_ROLES_Y_PERMISOS", "user groups", "GroupId", "GroupId,GroupName", "users,authorizations", "UGR1,OUSR", "CONFIRMED"),
    ("OUPT", "USUARIOS_ROLES_Y_PERMISOS", "permission tree", "PermId", "PermId,Name,ParentId", "users,authorizations", "UGR1,USR3", "LIKELY"),
    ("OHEM", "RRHH", "employee master", "empID", "empID,firstName,lastName,salesPrson,Active", "users,attribution,HR", "OUSR,OSLP", "CONFIRMED"),
    ("OADM", "CONFIGURACIÓN_SAP", "company-level credit and configuration", "singleton", "CreditLimt,OpenCredit,SalesLimit,DlnLimit,CreditDay", "credit,configuration", "OINV,ORDR,ODLN", "CONFIRMED"),
    ("OJDT", "CONTABILIDAD", "journal entry header", "TransId", "TransId,RefDate,TransType,UserSign,LocTotal,SyTotal", "finance,treasury,users", "JDT1,OINV,ORCT,OVPM,ODPS", "CONFIRMED"),
    ("JDT1", "CONTABILIDAD", "journal entry lines", "TransId+Line_ID", "TransId,Line_ID,Account,Debit,Credit,FCCurrency,FCDebit,FCCredit,ProfitCode", "finance,treasury,HR,WHT", "OJDT,OACT,ORCT,OVPM", "CONFIRMED"),
    ("OACT", "CONTABILIDAD", "chart of accounts and balances", "AcctCode", "AcctCode,AcctName,GroupMask,FatherNum,CurrTotal,ActCurr", "finance,treasury,HR,WHT", "JDT1,OJDT", "CONFIRMED"),
    ("ODPS", "CAJA_BANCOS", "deposit header", "DeposId", "DeposId,DeposDate,DeposType,Total,AcctCode,TransAbs", "treasury,cash_deposit", "OJDT,JDT1,OCHH,ORCT", "CONFIRMED"),
    ("OCHH", "CAJA_BANCOS", "check history/deposit linkage", "CheckKey", "CheckKey,CheckNum,DpstAbs", "treasury,cash_deposit", "ORCT,ODPS,OCHO", "CONFIRMED"),
    ("OCHO", "CAJA_BANCOS", "outgoing checks", "CheckKey", "CheckKey,CheckNum,CheckSum", "treasury", "OVPM,OCHH", "LIKELY"),
    ("ODSC", "CAJA_BANCOS", "bank/house bank configuration", "AbsEntry", "AbsEntry,GLAccount,Branch", "treasury", "DSC1,OACT", "CONFIRMED"),
    ("DSC1", "CAJA_BANCOS", "bank account configuration", "AbsEntry+LineId", "AbsEntry,GLAccount,AccountNo", "treasury", "ODSC,OACT", "CONFIRMED"),
    ("OBNK", "CAJA_BANCOS", "bank statement/reconciliation source", "BankMatchNo", "BankMatchNo,DueDate,Debit,Credit,ReconDate", "treasury", "OJDT,JDT1", "CONFIRMED"),
    ("OVPM", "CAJA_BANCOS", "outgoing payment header", "DocEntry", "DocEntry,DocNum,CardCode,DocDate,DocTotal,Canceled,TransId", "AP,treasury,debt", "VPM2,ITR1,OJDT,OPCH", "CONFIRMED"),
    ("VPM2", "CAJA_BANCOS", "outgoing payment invoice application", "DocNum+InvType+DocEntry", "DocNum,InvType,DocEntry,SumApplied", "AP,treasury", "OVPM,OPCH,ITR1", "CONFIRMED"),
    ("PCH5", "RETENCIONES", "AP withholding detail", "AbsEntry+LineNum", "AbsEntry,WTCode,TaxbleAmnt,WTAmnt", "WHT", "OPCH,OWHT,JDT1", "CONFIRMED"),
    ("PCH6", "RETENCIONES", "AP withholding totals", "AbsEntry", "AbsEntry,WTSum", "WHT", "OPCH,PCH5", "CONFIRMED"),
    ("VPM6", "RETENCIONES", "payment withholding totals", "DocNum", "DocNum,WTSum", "WHT", "OVPM,VPM2", "CONFIRMED"),
    ("OWHT", "RETENCIONES", "withholding configuration", "WTCode", "WTCode,WTName,Account", "WHT", "PCH5,PCH6,VPM6", "CONFIRMED"),
    ("@SO1_01LOGAUTORIZA", "USUARIOS_ROLES_Y_PERMISOS", "Retail One authorization/activity log", "event/folio candidate", "FOLIO,action,station,operator,event_time", "credit,users,channel", "OINV,@SO1_01VEN...", "CONFIRMED"),
    ("@SO1_01VENCREVENC", "CRÉDITO_Y_DEUDORES", "Retail One customer exception flag UDT", "CardCode candidate", "CardCode,VENCREVENC", "credit", "OCRD,OINV", "LIKELY"),
    ("@SO1_01COMPRA", "COMPRAS_Y_ABASTECIMIENTO", "Retail One purchase UDT (observed empty)", "DocEntry candidate", "document fields", "purchases", "OPOR,OPCH", "CONFIRMED"),
    ("@SO1_01COMPRADETALLE", "COMPRAS_Y_ABASTECIMIENTO", "Retail One purchase detail UDT (observed empty)", "DocEntry+LineNum candidate", "line fields", "purchases", "POR1", "CONFIRMED"),
    ("@SO1_01DEVOLCOMPRA", "COMPRAS_Y_ABASTECIMIENTO", "Retail One purchase return UDT (observed empty)", "DocEntry candidate", "document fields", "purchases", "ORPD,RPD1", "CONFIRMED"),
    ("@SO1_01COMPRAWEB", "COMPRAS_Y_ABASTECIMIENTO", "Retail One web purchase UDT (observed empty)", "DocEntry candidate", "document fields", "purchases", "OPOR,OPCH", "CONFIRMED"),
    ("@SO1_01FAVPROVEEDOR", "COMPRAS_Y_ABASTECIMIENTO", "Retail One preferred supplier UDT (observed empty)", "supplier/item candidate", "supplier fields", "purchases", "OCRD,OITM", "CONFIRMED"),
    ("@SO1_01SUGERENCOMPRA", "COMPRAS_Y_ABASTECIMIENTO", "Retail One purchase suggestion UDT (observed empty)", "item candidate", "suggestion fields", "purchases", "OITM,OPOR", "CONFIRMED"),
]

RELATIONSHIPS = [
    ("OINV", "DocEntry", "INV1", "DocEntry", "1:N", "invoice header to lines", "sales/financial gates + SQL invoice contract", "CONFIRMED"),
    ("ORIN", "DocEntry", "RIN1", "DocEntry", "1:N", "credit note header to lines", "financial credit-note gate", "CONFIRMED"),
    ("OQUT", "DocEntry", "QUT1", "DocEntry", "1:N", "quotation header to lines", "proforma/pricing investigation", "CONFIRMED"),
    ("OWOR", "DocEntry", "WOR1", "DocEntry", "1:N", "production order to historical component snapshot", "production schema + BOM gates", "CONFIRMED"),
    ("OITT", "Code", "ITT1", "Father", "1:N", "current BOM header to components", "recipe/BOM gate", "CONFIRMED"),
    ("OPOR", "DocEntry", "PCH1", "BaseEntry", "1:N", "PO to vendor invoice lines, BaseType=22", "purchase discovery P0.1", "CONFIRMED"),
    ("OPCH", "DocEntry", "PDN1", "BaseEntry", "1:N", "vendor invoice to goods receipt lines, BaseType=18", "purchase discovery P0.1", "CONFIRMED"),
    ("OPOR", "DocEntry", "PDN1", "BaseEntry", "1:N", "direct PO to goods receipt, BaseType=22", "purchase discovery", "CONFIRMED"),
    ("OINV", "DocEntry", "ITR1", "SrcObjAbs", "1:N", "invoice settlement member, SrcObjTyp=13", "financial reconciliation + credit gates", "CONFIRMED"),
    ("ORCT", "DocEntry", "ITR1", "SrcObjAbs", "1:N", "incoming payment settlement member, SrcObjTyp=24", "financial reconciliation gate", "CONFIRMED"),
    ("OITR", "ReconNum", "ITR1", "ReconNum", "1:N", "reconciliation header to members and ReconDate", "financial reconciliation gate", "CONFIRMED"),
    ("OINV", "TransId", "OJDT", "TransId", "1:1", "invoice accounting entry when present", "financial/traceability gates", "LIKELY"),
    ("ORCT", "TransId", "OJDT", "TransId", "1:1", "incoming payment accounting entry", "treasury and cross traceability", "CONFIRMED"),
    ("OVPM", "TransId", "OJDT", "TransId", "1:1", "outgoing payment accounting entry", "AP/treasury gates", "CONFIRMED"),
    ("ODPS", "TransAbs", "OJDT", "TransId", "1:1", "deposit accounting entry", "treasury gate", "CONFIRMED"),
    ("IGE1", "BaseEntry", "OWOR", "DocEntry", "N:1", "actual component issue to production order, BaseType=202", "production schema gate", "CONFIRMED"),
    ("IGN1", "BaseEntry", "OWOR", "DocEntry", "N:1", "actual finished output to production order, BaseType=202", "production schema gate", "CONFIRMED"),
    ("IGE1", "BaseRef", "OINM", "BASE_REF", "N:0..1", "issue to inventory ledger where populated", "production output/consumption gates", "LIKELY"),
    ("IGN1", "BaseRef", "OINM", "BASE_REF", "N:0..1", "receipt to inventory ledger where populated", "production output/consumption gates", "LIKELY"),
    ("OWTR", "DocEntry", "WTR1", "DocEntry", "1:N", "transfer header to lines", "warehouse transfer gate", "CONFIRMED"),
    ("WTR1", "DocEntry+LineNum", "OINM", "source movement", "1:2", "transfer origin out and destination in", "warehouse transfer gate TT67", "CONFIRMED"),
    ("OITW", "ItemCode+WhsCode", "OINM", "ItemCode+Warehouse", "1:N", "current stock reconciled to movement ledger", "material stock gate", "CONFIRMED"),
    ("OUSR", "USERID", "OHEM", "userCode/employee link", "0..1:0..1", "SAP user to employee where populated", "users and attribution gate", "CONFIRMED"),
    ("OHEM", "salesPrson", "OSLP", "SlpCode", "N:1", "employee to salesperson", "users and attribution gate", "CONFIRMED"),
    ("OUSR", "USERID", "USR5", "USERID", "1:N", "user to activity events", "users gate; aggregate before joins", "CONFIRMED"),
    ("OUSR", "USERID", "USR3", "USERID", "1:N", "direct permissions", "users gate; current only", "CONFIRMED"),
    ("OUGR", "GroupId", "UGR1", "GroupId", "1:N", "group permissions", "users gate; current only", "CONFIRMED"),
    ("OINV", "CardCode", "OCRD", "CardCode", "N:1", "invoice business partner", "sales/credit/customer gates", "CONFIRMED"),
    ("OWTR", "DocEntry", "IBT1", "BaseEntry", "1:N", "batch trace for transfer when batch data exists", "transfer gate", "LIKELY"),
    ("OPCH", "DocEntry", "ITR1", "SrcObjAbs", "1:N", "AP settlement members", "AP reconciliation gate", "CONFIRMED"),
    ("OVPM", "DocEntry", "ITR1", "SrcObjAbs", "1:N", "outgoing payment settlement members", "AP reconciliation gate", "CONFIRMED"),
]

RULES = [
    ("BR-SALES-001", "VENTAS", "What is a valid invoice?", "OINV", "CANCELED='N' is active; Y is canceled original; C is reversal", "cancellation semantics + financial invoice contract", "CONFIRMED"),
    ("BR-SALES-002", "VENTAS", "Which date describes the document and cancellation?", "OINV", "DocDate is document date; UpdateDate/UpdateTS captures later update/cancellation", "temporal cancellation gates", "CONFIRMED"),
    ("BR-SALES-003", "VENTAS", "How is a proforma linked to an invoice?", "INV1,QUT1", "BaseType=23 and BaseEntry+BaseLine; price/discount differences are measured at line grain", "proforma pricing SQL and report", "CONFIRMED"),
    ("BR-CREDIT-001", "CRÉDITO_Y_DEUDORES", "What is settlement authority?", "OITR,ITR1", "ITR1/OITR is the settlement ledger; RCT2 is a payment application reference and cannot be sole authority", "FINANCIAL-003/004 + credit exception", "CONFIRMED"),
    ("BR-CREDIT-002", "CRÉDITO_Y_DEUDORES", "How is historical debt reconstructed?", "OINV,ORIN,ITR1,OITR,ORCT", "as-of T uses ReconDate and active settlement/NC events; effective due date is validated against INV6 where present", "credit exception/open risk gates", "CONFIRMED"),
    ("BR-CREDIT-003", "CRÉDITO_Y_DEUDORES", "What does SAP configuration prove?", "OADM,OCRD", "CreditLimt/SalesLimit and CreditLine describe configuration/exposure; configuration does not prove an operational approval", "credit control gate", "CONFIRMED"),
    ("BR-CREDIT-004", "CRÉDITO_Y_DEUDORES", "Can delivery be treated as credit-controlled?", "OADM,ODLN", "DlnLimit='N' observed; delivery-flow exceptions are investigated, not called a technical exemption", "credit control + exception cases", "CONFIRMED"),
    ("BR-PURCHASE-001", "COMPRAS_Y_ABASTECIMIENTO", "What is the canonical purchase chain?", "OPOR,POR1,OPCH,PCH1,OPDN,PDN1", "BaseEntry→DocEntry; dominant observed flow is PO→invoice→receipt, with direct PO→receipt cases", "purchase discovery P0.1", "CONFIRMED"),
    ("BR-PURCHASE-002", "COMPRAS_Y_ABASTECIMIENTO", "What is purchase type?", "OPOR,OCRD", "OPOR.U_TIPOCOMPRA operationally classifies LF/LP/IMP/SERV/SAA; OCRD.Country alone does not classify imports", "purchase discovery", "CONFIRMED"),
    ("BR-PURCHASE-003", "COMPRAS_Y_ABASTECIMIENTO", "Is ordered quantity in transit?", "POR1,OPDN", "OpenQty>0 means ordered/not received in SAP; shipment/customs status remains unresolved", "purchase discovery", "CONFIRMED"),
    ("BR-STOCK-001", "STOCK_E_INVENTARIOS", "What do stock fields mean?", "OITW,OINM", "OnHand is physical current position; IsCommited is committed; OnOrder is separate ordered position; historical stock is reconstructed from OINM", "material stock gate", "CONFIRMED"),
    ("BR-STOCK-002", "TRANSFERENCIAS_Y_DEPÓSITOS", "Which warehouse is origin/destination?", "WTR1,OWTR", "FromWhsCod=origin, WhsCode=destination, Quantity=transfer quantity", "warehouse transfer gate", "CONFIRMED"),
    ("BR-STOCK-003", "TRANSFERENCIAS_Y_DEPÓSITOS", "Does a transfer prove physical shipment?", "OWTR,WTR1,OINM", "No: TT67 preserves accounting out/in, but PHYSICAL_DISPATCH_SEMANTICS is ACCOUNTING_ONLY", "warehouse transfer + physical lead-time gates", "CONFIRMED"),
    ("BR-PROD-001", "PRODUCCIÓN", "What is historical BOM truth?", "OWOR,WOR1", "WOR1 is the order-time recipe snapshot and has priority over current ITT1 for historical analysis", "recipe/BOM gate", "CONFIRMED"),
    ("BR-PROD-002", "PRODUCCIÓN", "How is expected consumption calculated?", "OWOR,WOR1", "(BaseQtyNum/BaseQtyDen)×PlannedQty; compare with net IGE1 quantity", "production reconciliation gate", "CONFIRMED"),
    ("BR-PROD-003", "PRODUCCIÓN", "What is actual consumption/output?", "IGE1,IGN1", "net consumption=SUM(IGE1.Quantity) BT=202; output=SUM(IGN1.Quantity) BT=202", "production consumption/output gates", "CONFIRMED"),
    ("BR-PROD-004", "PRODUCCIÓN", "Does Released mean unfinished?", "OWOR,IGE1,IGN1", "No in Telchi; Status='L' frequently has complete consumption/output. IGN1 is output truth", "production schema/output gates", "CONFIRMED"),
    ("BR-MRP-001", "FORECAST_Y_ESTACIONALIDAD", "What does an MRP parameter mean?", "OITM,OITW,OFCT,FCT1", "CONFIGURED is not VALIDATED/OBSERVED operational use; SafetyStock was not confirmed as a physical standard field", "MRP configuration audit", "CONFIRMED"),
    ("BR-MRP-002", "FORECAST_Y_ESTACIONALIDAD", "What is forecast coverage?", "OFCT,FCT1", "forecast rows and active use are measured separately; ActiveStatus is not inferred when not exposed", "MRP configuration/forecast gap", "CONFIRMED"),
    ("BR-USERS-001", "USUARIOS_ROLES_Y_PERMISOS", "What does OJDT.UserSign mean?", "OJDT,OINV,ORCT", "it is commonly the source transaction user; only TransType=59 is treated as manual journal entry", "users cross-traceability gate", "CONFIRMED"),
    ("BR-USERS-002", "USUARIOS_ROLES_Y_PERMISOS", "Can historical authorization be proven?", "OUSR,USR3,UGR1,USR5", "no: current permission state cannot prove historical authorization", "users gate", "CONFIRMED"),
    ("BR-USERS-003", "ACTIVIDAD_DE_USUARIOS", "Is one USR5 row one business operation?", "USR5", "no; log events, document operations and business transactions are distinct", "users gate", "CONFIRMED"),
    ("BR-FIN-001", "CONTABILIDAD", "How is financial position/P&L reconstructed?", "OACT,OJDT,JDT1", "classify accounts using SAP hierarchy while preserving Team360 financial classification; exclude closing -2/-3 from current P&L flows", "financial position/P&L gate", "CONFIRMED"),
    ("BR-FIN-002", "CAJA_BANCOS", "How are deposits traced?", "ORCT,OCHH,ODPS,OJDT", "checks have a documentary chain; cash→deposit lacks direct FK and only unique aggregate matches are strong", "treasury/cash deposit gates", "CONFIRMED"),
    ("BR-FIN-003", "RETENCIONES", "Does configured WHT prove actual withholding?", "OWHT,PCH5,PCH6,VPM2,VPM6,JDT1", "no; configured accounts without activity do not prove a transactional withholding path", "WHT traceability gate", "CONFIRMED"),
    ("BR-HR-001", "RRHH", "Does SAP contain detailed payroll?", "OHEM,OACT,JDT1", "OHEM and GL labor cost are observed; a detailed payroll object was not identified", "HR/payroll reconciliation gate", "CONFIRMED"),
]

METRICS = [
    ("M-SALES-VOLUME", "sales invoices", "VENTAS", "1.81M invoices; channel split 86.1% Retail One / 8.5% DMS / 5.4% SAP direct", "2026-08", "active OINV; U_ORIGIN/U_SO1_01RETAILONE", "OINV", "users_roles_authorizations_v1_report.md", "YES"),
    ("M-CREDIT-BASELINE", "sales with overdue unpaid at sale date", "CRÉDITO_Y_DEUDORES", "2,318 exact; 287 prior baseline revalidated; 19 unresolved in the 287 operational subset", "2026-01-01..2026-09-01", "as-of settlement and active documents", "OINV,ORIN,ORCT,ITR1,OITR", "credit_exception_cases_v1_report.md", "YES"),
    ("M-CREDIT-OPEN", "open risk", "CRÉDITO_Y_DEUDORES", "Bs 252,973 open; Bs 175,928.88 not due; Bs 77,044.12 overdue", "2026-09-01", "287-case baseline", "OINV,ORIN,ITR1,OITR", "credit_open_risk_aging_v1_report.md", "YES"),
    ("M-PURCHASE-CHAIN", "purchase chain coverage", "COMPRAS_Y_ABASTECIMIENTO", "PO→AP 90,959/90,959; AP→GR 87,577/87,577; direct PO→GR 54/54", "2026-08-27", "valid active/documented links", "OPOR,POR1,OPCH,PCH1,OPDN,PDN1", "purchase_data_discovery_v1_report.md", "YES"),
    ("M-PURCHASE-LEAD", "purchase lead time p90", "COMPRAS_Y_ABASTECIMIENTO", "LF 4d; LP 43d; IMP 82d; SAA 34d; global first receipt p90 5d", "2022-01..2026-08", "first receipt, document dates", "OPOR,OPCH,OPDN,POR1,PCH1,PDN1", "purchase_lead_time_v1_report.md", "YES"),
    ("M-STOCK", "stock position", "STOCK_E_INVENTARIOS", "16,793 items; 82 warehouses; OnOrder 1,790,139; IsCommited 487,292", "2026-08-27", "OITW current", "OITW,OINM,OWHS", "material_stock_position_v1_report.md", "YES"),
    ("M-TRANSFER", "transfer conservation", "TRANSFERENCIAS_Y_DEPÓSITOS", "36,210/36,210 transfer lines conserved in OINM TT67; 0 same-warehouse", "2026-08-26", "active transfer documents", "OWTR,WTR1,OINM", "warehouse_transfer_traceability_v1_report.md", "YES"),
    ("M-PROD-ORDERS", "production census", "PRODUCCIÓN", "20,777 OWOR; 140,391 WOR1 lines; 20,487 standard orders", "2022-04..2026-08", "production schema universe", "OWOR,WOR1", "production_schema_discovery_v1_report.md", "YES"),
    ("M-PROD-CONSUMPTION", "production issue method", "PRODUCCIÓN", "67.5% manual / 32.5% backflush; 134,291/134,292 IssuedQty reconciled", "2026-08-26", "production lines with actual issues", "WOR1,IGE1", "production_component_consumption_v1_report.md", "YES"),
    ("M-PROD-OUTPUT", "production output", "PRODUCCIÓN", "19,654/20,487 orders with CmpltQty reconciled to IGN1; 842 without output", "2026-08-26", "BT=202 output", "OWOR,IGN1", "production_output_traceability_v1_report.md", "YES"),
    ("M-MRP-COVERAGE", "MRP configuration coverage", "FORECAST_Y_ESTACIONALIDAD", "LeadTime 69.5%; SafetyStock 0%; forecast 29.1%; BOM 6.2% of item universe", "2026-08-26", "16,853 items / 82 warehouses", "OITM,OITW,OITT,ITT1,OFCT,FCT1", "telchi_mrp_configuration_audit_v1_report.md", "YES"),
    ("M-SEASONALITY", "product seasonality coverage", "FORECAST_Y_ESTACIONALIDAD", "10,775 items; high/medium volume coverage 90.0%; 4,168 insufficient", "2026-08-27", "monthly net OINV−ORIN", "OINV,INV1,ORIN,RIN1", "product_seasonality_v1_report.md", "YES"),
    ("M-USERS", "SAP users/activity", "USUARIOS_ROLES_Y_PERMISOS", "170 users; 78 active; 92 blocked; 3,176,076 USR5 rows; 16 superusers", "2026-08-26", "OUSR/USR5 census", "OUSR,USR3,UGR1,USR5,OHEM,OSLP", "users_roles_authorizations_v1_report.md", "YES"),
    ("M-FIN-AR", "open AR", "CONTABILIDAD", "2,067 documents; Bs 4,092,786.95; overdue Bs 1,477,647.75", "2026-09-10", "active AR at cut", "OINV,ORIN,ITR1,OITR", "telchi_financial_forecast_liquidity_scenarios_v1_report.md", "YES"),
    ("M-FIN-AP", "open AP", "CONTABILIDAD", "636 documents; Bs 9,547,420.94 + USD 148,291.25", "2026-09-10", "active AP at cut", "OPCH,ORPD,ITR1,OVPM", "telchi_financial_forecast_liquidity_scenarios_v1_report.md", "YES"),
    ("M-FIN-BS", "balance sheet reconciliation", "CONTABILIDAD", "Assets Bs 86,107,745.15; liabilities Bs 21,498,186.57; equity Bs 64,609,558.58; gap 0", "2026-09-10", "2026 open period", "OACT,OJDT,JDT1", "telchi_balance_sheet_pnl_reconstruction_v1_report.md", "YES"),
    ("M-FIN-RESULT", "financial result", "CONTABILIDAD", "−Bs 1,414,305.12 reproduced; bridge post-close −Bs 104.59", "2026-09-10", "2026 YTD", "OACT,OJDT,JDT1", "telchi_financial_debt_and_financial_result_v1_report.md", "YES"),
    ("M-TREASURY", "treasury document volumes", "CAJA_BANCOS", "1,804,931 ORCT; 40,272 OVPM; 14,593 ODPS", "2026-09-09", "active/cancelled separated", "ORCT,OVPM,ODPS,OJDT,JDT1", "telchi_treasury_cash_bank_deposit_v1_report.md", "YES"),
    ("M-HR-COST", "HR expense in GL", "RRHH", "Bs 13,600,311.25 HR-classified YTD expense; detailed payroll not observed", "2026-09-09", "classified GL accounts", "OHEM,OACT,JDT1", "telchi_hr_payroll_accounting_traceability_v1_report.md", "YES"),
]

MAPPINGS = [
    ("MAP-001", "movProductSB1", "OINM + source documents", "TransNum/DocLineNum vs SAP movement keys; ItemCode; Warehouse/WhsCode; TransType/BASE_REF", "legacy line movement vs SAP ledger; legacy includes enriched joins and duplicate candidate keys", "2022-04..2024-05 vs SAP current/historical window", "source lineage not formal in Parquet; not every movement has document FK", "LIKELY", "TELCHI_HISTORICAL_DATA_INVENTORY_V1.md; production/stock/transfer reports"),
    ("MAP-002", "saleSB1Product", "OINV + INV1", "DocEntry, ItemCode, document/date/amount fields", "legacy enriched invoice-line family; WhsCode optional/null in some -h files", "2018-01..2024-05; SAP investigations extend beyond", "snapshot overlap and no formal extractor lineage", "LIKELY", "TELCHI_HISTORICAL_DATA_INVENTORY_V1.md; financial invoice contract"),
    ("MAP-003", "ncB1Product", "ORIN + RIN1", "DocEntry/line/item/date/amount candidates", "legacy NC family with fu_* naming variants; semantic equivalence not fully reconciled", "2022-04..2024-06", "coverage and schema variants", "POSSIBLE", "TELCHI_HISTORICAL_DATA_INVENTORY_V1.md; financial credit-note reports"),
    ("MAP-004", "productSB1", "OITM", "ItemCode and product attributes", "master snapshot vs current SAP master; validity history absent", "2022-03..2024-06", "no temporal master lineage", "LIKELY", "TELCHI_HISTORICAL_DATA_INVENTORY_V1.md; material stock/MRP"),
    ("MAP-005", "clientSB1", "OCRD", "CardCode/CardName and customer attributes", "master snapshot; customer history and as-of validity absent", "static historical snapshot", "no temporal master lineage", "LIKELY", "TELCHI_HISTORICAL_DATA_INVENTORY_V1.md; customer/credit reports"),
    ("MAP-006", "owhsSB1", "OWHS", "WhsCode/warehouse names", "small historical warehouse master vs 82-warehouse current census", "static/unknown", "mapping validity and retired warehouses", "POSSIBLE", "TELCHI_HISTORICAL_DATA_INVENTORY_V1.md; production schema"),
    ("MAP-007", "wareHouseSB1", "OWHS", "warehouse code/name fields", "enriched warehouse family; likely master/reference", "2021-12..2024-06", "schema and temporal semantics not formal", "POSSIBLE", "TELCHI_HISTORICAL_DATA_INVENTORY_V1.md"),
    ("MAP-008", "paymentB1", "ORCT + ITR1/OITR", "DocEntry, amount, dates, reconciliation fields", "payment snapshot vs settlement ledger; RCT2 must not be assumed sufficient", "2022-04..2023-05", "snapshot overlap and settlement semantics", "POSSIBLE", "TELCHI_HISTORICAL_DATA_INVENTORY_V1.md; financial reconciliation"),
    ("MAP-009", "reconB1", "OITR + ITR1", "ReconNum/LineSeq and reconciliation amounts/dates", "legacy reconciliation family likely closest to SAP settlement grain", "2022-04..2023-05", "source/extractor and cancellation history unknown", "LIKELY", "TELCHI_HISTORICAL_DATA_INVENTORY_V1.md; financial reconciliation"),
    ("MAP-010", "productTracking", "OBTN/IBT1 and/or legacy-only tracking", "product/tracking date/lot candidates", "no direct complete equivalence demonstrated", "2019-01..2022-04", "lot/serial semantics and SAP coverage", "UNKNOWN", "TELCHI_HISTORICAL_DATA_INVENTORY_V1.md"),
]

GAPS = [
    ("GAP-001", "LINEAGE_UNKNOWN", "All legacy Parquet", "No formal source system, query, extractor identity, watermark, timezone or snapshot contract in footers", "next gate lineage contract", "HIGH"),
    ("GAP-002", "TEMPORAL_GAP", "Snapshot families", "Filename date and contained business dates are distinct; concatenation can double count", "snapshot/as-of policy", "HIGH"),
    ("GAP-003", "SEMANTICS_UNKNOWN", "movProductSB1 ↔ OINM", "candidate join is rich but not universal; 181,384 duplicate candidate keys", "reconcile grain and document coverage", "HIGH"),
    ("GAP-004", "HISTORICAL_NOT_AVAILABLE", "master Parquet ↔ SAP masters", "historical validity of OITM/OCRD/OWHS and warehouse-office mapping is absent", "temporal master policy", "HIGH"),
    ("GAP-005", "SAP_NOT_YET_INVESTIGATED", "Purchasing request approval / MRP execution", "tables/configuration discovered, but operational approval and MRP run history are not demonstrated", "targeted investigation only if needed", "MEDIUM"),
    ("GAP-006", "SEMANTICS_UNKNOWN", "OFCT/FCT1", "configured/observed forecast rows do not prove active operational forecast use", "forecast contract", "HIGH"),
    ("GAP-007", "SEMANTICS_UNKNOWN", "OITM/OITW safety stock", "SafetyStock field/operational semantics not confirmed; ReorderPnt is only a labeled proxy", "MRP semantics decision", "HIGH"),
    ("GAP-008", "SAP_NOT_YET_INVESTIGATED", "MRP/forecast history", "no execution log or historical parameter versioning located", "point validation with SAP/process owner", "MEDIUM"),
    ("GAP-009", "SAP_NOT_YET_INVESTIGATED", "Lotes/series", "IBT1/OBTN observed in selected paths; complete sales/production lot/serial coverage not closed", "lot/serial scope gate", "MEDIUM"),
    ("GAP-010", "SEMANTICS_UNKNOWN", "production → dispatch", "no BaseType=202 FK; temporal ItemCode/warehouse/date link is heuristic", "business model must preserve heuristic", "HIGH"),
    ("GAP-011", "SEMANTICS_UNKNOWN", "physical lead time", "OWTR/OINM accounting event does not prove physical dispatch/receipt", "logistics evidence contract", "HIGH"),
    ("GAP-012", "SECURITY_PENDING", "users/permissions", "historical authorization unavailable; future security-before-retrieval not implemented", "RBAC/row/column/metric policy", "HIGH"),
    ("GAP-013", "SAP_NOT_YET_INVESTIGATED", "approvals/exceptions", "management approvals external to SAP; retail log linkage is heuristic in part", "external evidence contract", "MEDIUM"),
    ("GAP-014", "SAP_NOT_YET_INVESTIGATED", "detailed payroll", "OHEM and GL cost observed, but no detailed SAP payroll object identified", "external payroll boundary", "HIGH"),
    ("GAP-015", "SEMANTICS_UNKNOWN", "WHT", "configured OWHT accounts and WHT columns do not establish an active transactional path", "WHT source authority", "HIGH"),
    ("GAP-016", "SEMANTICS_UNKNOWN", "bank reconciliation", "OBNK exists but no external bank balance reconciliation was demonstrated", "bank statement contract", "MEDIUM"),
    ("GAP-017", "HISTORICAL_NOT_AVAILABLE", "legacy purchaseExpense/productTransform/cash", "SAP equivalents are partial or not yet semantically reconciled", "legacy↔SAP mapping gate", "MEDIUM"),
    ("GAP-018", "TEMPORAL_GAP", "cancellations and payments", "current SAP can reconstruct selected as-of states, but historical Parquet coverage and watermarks differ", "as-of reconciliation", "HIGH"),
]

PRODUCTS = [
    ("inventory_movements", "STOCK_E_INVENTARIOS", "OINM + document lineage; movProductSB1 correspondence", "CONFIRMED/PARTIAL", "inventory", "cost; warehouse scope; movement user"),
    ("sales_lines", "VENTAS", "OINV/INV1 with cancellation and channel semantics", "CONFIRMED", "sales", "price; cost; margin; customer"),
    ("sales_document_chain", "VENTAS", "quotation/order/delivery/invoice/credit-note chain", "CONFIRMED/PARTIAL", "sales", "customer; price; discount"),
    ("customer_credit_state", "CRÉDITO_Y_DEUDORES", "as-of invoice/NC/payment/reconciliation/aging", "CONFIRMED", "credit", "credit_limit; customer_debt; customer"),
    ("purchase_cycle", "COMPRAS_Y_ABASTECIMIENTO", "request/order/invoice/receipt/return with BaseEntry lineage", "CONFIRMED", "purchases", "purchase_price; supplier"),
    ("production_orders", "PRODUCCIÓN", "OWOR/WOR1/IGE1/IGN1 and normalized reconciliation", "CONFIRMED/PARTIAL", "production", "cost; output; component"),
    ("bom_and_component_usage", "BOM_PRODUCCIÓN", "OITT/ITT1 plus order-time WOR1", "CONFIRMED/PARTIAL", "production", "cost; formulation"),
    ("stock_current_and_history", "STOCK_E_INVENTARIOS", "OITW current and OINM reconstruction", "CONFIRMED", "inventory", "cost; warehouse"),
    ("warehouse_transfers", "TRANSFERENCIAS_Y_DEPÓSITOS", "OWTR/WTR1/OINM TT67", "CONFIRMED/HEURISTIC_PHYSICAL", "inventory", "warehouse; user"),
    ("forecast_and_mrp_parameters", "FORECAST_Y_ESTACIONALIDAD", "OFCT/FCT1 and OITM/OITW configuration", "CONFIGURED_NOT_OPERATIONAL_PROOF", "configuration", "forecast; policy"),
    ("users_activity_and_capabilities", "USUARIOS_ROLES_Y_PERMISOS", "OUSR/USR3/UGR1/OUGR/USR5/OHEM/OSLP", "CONFIRMED_CURRENT_ONLY", "users", "user_activity; authorization"),
    ("gl_ar_ap_treasury", "CONTABILIDAD", "OACT/OJDT/JDT1 plus AR/AP and treasury chains", "CONFIRMED/PARTIAL", "finance", "bank_account; salary; debt"),
]

SECURITY = [
    ("inventory", "inventory", "warehouse, ItemCode, cost", "candidate warehouse/organizational scope", "administrator/all in this gate"),
    ("sales", "sales", "customer, price, cost, margin", "customer/branch/channel candidate", "administrator/all in this gate"),
    ("purchases", "purchases", "supplier, purchase_price, cost", "supplier/branch candidate", "administrator/all in this gate"),
    ("production", "production", "formulation, cost, output", "plant/warehouse candidate", "administrator/all in this gate"),
    ("credit", "credit", "credit_limit, customer_debt", "customer/portfolio candidate", "administrator/all in this gate"),
    ("finance", "finance", "bank_account, debt, margin", "company/legal-entity candidate", "administrator/all in this gate"),
    ("hr", "hr", "salary, employee identity", "organizational candidate", "administrator/all in this gate"),
    ("users", "users", "user_activity, authorization", "organizational candidate", "administrator/all in this gate"),
    ("configuration", "configuration", "MRP/credit configuration", "company/warehouse candidate", "administrator/all in this gate"),
]


def _source_files() -> list[Path]:
    paths = []
    backend_tests = ROOT / "SrvRestAstroLS_v1/backend/tests"
    for base in (DOCS, VALIDATION, backend_tests):
        paths.extend(
            p for p in base.rglob("*")
            if p.is_file()
            and p.suffix.lower() in {".md", ".py", ".sql", ".json", ".yaml", ".yml", ".csv", ".txt"}
            and p.parent != Path(__file__).resolve().parent
            and p.name != "TELCHI_SAP_KNOWLEDGE_INVENTORY_V1.md"
        )
    return sorted(set(paths))


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _status(gate: str) -> str:
    for suffix in STATUS_SUFFIXES:
        if gate.endswith(suffix):
            return suffix[1:]
    return "UNKNOWN"


def _gate_rows() -> list[dict[str, str]]:
    occurrences: dict[str, list[Path]] = {}
    for path in _source_files():
        text = _read(path)
        for gate in set(GATE_RE.findall(text)):
            occurrences.setdefault(gate, []).append(path)

    rows = []
    for gate in sorted(occurrences):
        paths = occurrences[gate]
        docs = [_rel(p) for p in paths if p.suffix.lower() == ".md"]
        code = [_rel(p) for p in paths if p.suffix.lower() in {".py", ".sql", ".json", ".yaml", ".yml"}]
        corpus = "\n".join(_read(p) for p in paths)
        read_only = "YES" if re.search(r"SAP_WRITE_COUNT\s*[=:]\s*0|HANA writes.*(?:ZERO|0)|READ ONLY|SELECT-only", corpus, re.I) else "UNKNOWN"
        sap_access = "YES" if re.search(r"SAP|HANA", corpus, re.I) else "UNKNOWN"
        date_match = re.search(r"(?:Date|Fecha|AS_OF|Evidencia)\s*[:=]\s*(20\d\d[-/]\d\d[-/]\d\d)", corpus, re.I)
        rows.append({
            "gate_id": gate,
            "title": re.sub(r"_(?:PASS|DEGRADED|FAIL|INCOMPLETE|HISTORICAL|UNKNOWN|PARTIAL)$", "", gate).replace("_", " ").title(),
            "domain": _domain_for_gate(gate),
            "status": _status(gate),
            "date_if_known": date_match.group(1) if date_match else "UNKNOWN",
            "source_document": "; ".join(docs[:8]) or "UNKNOWN",
            "source_code": "; ".join(code[:8]) or "UNKNOWN",
            "evidence_path": f"repo:{_rel(paths[0])}; external:{EVIDENCE_ROOT}/validation (if present)",
            "sap_access": sap_access,
            "read_only": read_only,
            "tables": "; ".join(sorted(_tables_in_text(corpus))) or "UNKNOWN",
            "business_question": _domain_for_gate(gate),
            "main_result": "Status explicitly recorded in source corpus; see source document.",
            "confidence": "CONFIRMED" if _status(gate) in {"PASS", "DEGRADED", "FAIL", "INCOMPLETE", "HISTORICAL"} else "UNKNOWN",
        })
    return rows


def _domain_for_gate(gate: str) -> str:
    mapping = {
        "CREDIT": "CRÉDITO_Y_DEUDORES", "FINANCIAL": "CONTABILIDAD", "TREASURY": "CAJA_BANCOS",
        "PURCHASE": "COMPRAS_Y_ABASTECIMIENTO", "PRODUCTION": "PRODUCCIÓN", "RECIPE": "BOM_PRODUCCIÓN",
        "STOCK": "STOCK_E_INVENTARIOS", "WAREHOUSE": "TRANSFERENCIAS_Y_DEPÓSITOS", "INVENTORY": "MOVIMIENTOS_DE_INVENTARIO",
        "MRP": "FORECAST_Y_ESTACIONALIDAD", "FORECAST": "FORECAST_Y_ESTACIONALIDAD", "SEASONALITY": "FORECAST_Y_ESTACIONALIDAD",
        "USER": "USUARIOS_ROLES_Y_PERMISOS", "RETAIL": "USUARIOS_ROLES_Y_PERMISOS", "HR": "RRHH",
        "PROFORMA": "COTIZACIONES_PROFORMAS", "COMMERCIAL": "VENTAS", "SALES": "VENTAS", "TEMPORAL": "TRAZABILIDAD_DOCUMENTAL",
        "AP_": "COMPRAS_Y_ABASTECIMIENTO", "CASH": "CAJA_BANCOS", "GL_": "CONTABILIDAD",
    }
    for key, domain in mapping.items():
        if key in gate:
            return domain
    return "TELCHI_SAP_CROSS_DOMAIN"


TABLE_TOKEN_RE = re.compile(r"(?<![A-Z0-9_])(?:@[A-Z0-9_]+|[A-Z][A-Z0-9_]{2,})(?![A-Z0-9_])")


def _tables_in_text(text: str) -> set[str]:
    known = {row[0] for row in TABLE_SPECS}
    known.update({"RDR1", "OPCH", "OVPM", "VPM2", "OUGR", "OUPT", "OWHT"})
    return set(TABLE_TOKEN_RE.findall(text)).intersection(known)


def _write_csv(name: str, fieldnames: list[str], rows: Iterable[dict | tuple]) -> None:
    path = OUTPUT / name
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(fieldnames)
        for row in rows:
            writer.writerow(row.values() if isinstance(row, dict) else row)


def _md_table(headers: list[str], rows: Iterable[Iterable[str]], limit: int | None = None) -> str:
    values = list(rows)
    if limit is not None:
        values = values[:limit]
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in values:
        out.append("| " + " | ".join(str(x).replace("|", "\\|") for x in row) + " |")
    return "\n".join(out)


def _report(gates: list[dict[str, str]], evidence_file_count: int) -> str:
    status_counts = Counter(row["status"] for row in gates)
    table_names = [row[0] for row in TABLE_SPECS]
    relationship_rows = RELATIONSHIPS
    rule_rows = RULES
    metric_rows = METRICS
    mapping_rows = MAPPINGS
    gap_rows = GAPS
    product_rows = PRODUCTS
    return f"""# TELCHI DATA LAKE — SAP KNOWLEDGE INVENTORY V1

## A. Gate

**DEGRADED — `TELCHI_SAP_KNOWLEDGE_INVENTORY_V1_DEGRADED`**

La revisión documental y de evidencia cerró el inventario, pero no puede declararse
PASS porque permanecen gaps materiales de lineage/snapshots, autorización histórica,
uso operacional de MRP/forecast, nómina detallada, WHT transaccional y algunos vínculos
físicos/temporales. No se inventaron conclusiones para compensarlos.

**Scope:** `ENTITY=TELCHI`; `STAGE=INVESTIGATION`; `SOURCE=SAP_HANA + LEGACY_DS + EXTERNAL_FILES`.
El gate consultó primero código, SQL, tests, reportes, JSON/YAML y manifests. No se
abrió una sesión SAP/HANA nueva.

## B. Resumen ejecutivo

- Se revisaron sistemáticamente los artefactos bajo `investigation/docs` y `investigation/validation`, además del manifest externo Telchi.
- Se catalogaron **{len(gates)} identificadores de gates** (incluye estados históricos y gates referenciados; no se deduplican estados PASS/DEGRADED/FAIL como si fueran la misma evidencia).
- El catálogo contiene **{len(TABLE_SPECS)} tablas/objetos SAP**, **{len(relationship_rows)} relaciones**, **{len(rule_rows)} reglas** y **{len(metric_rows)} métricas baseline**.
- Ventas, crédito/as-of, compras, producción, stock/transferencias, usuarios y contabilidad tienen evidencia HANA previa reproducible.
- Las piezas críticas del Gate 1, `movProductSB1` y `saleSB1Product`, conservan correspondencias probables pero no equivalencias confirmadas automáticamente.
- La cadena de compras `PO→AP→GR` y la cadena de producción `BOM→OWOR→IGE1/IGN1→OINM` están especialmente bien cerradas.
- `OITW` es estado actual; `OINM` permite reconstrucción histórica, pero la correspondencia con snapshots legacy aún requiere política temporal.
- MRP/forecast registra configuración y observaciones, no prueba de ejecución operacional ni de vigencia histórica.
- El histórico de autorización SAP no existe en la evidencia; la seguridad futura queda pendiente y no se implementó.
- Los números baseline se preservan para regresión futura, no se proponen como filas de Parquet nuevas.
- El siguiente gate debe aprobar modelo canónico, lineage, snapshots y fronteras de producto antes de diseñar físico.

## C. Método, seguridad y fuentes

Orden aplicado:

```text
EVIDENCIA EXISTENTE → CONOCIMIENTO VALIDADO → GAPS/UNKNOWN → SAP puntual si imprescindible
```

Fuentes revisadas:

- Workspace: `SrvRestAstroLS_v1/backend/modules/telchi/investigation/`.
- Gate 1, sin modificar: `docs/TELCHI_HISTORICAL_DATA_INVENTORY_V1.md`.
- Evidencia externa disponible: `{EVIDENCE_ROOT}`; archivos visibles en manifest/árbol: **{evidence_file_count}**.
- Se inspeccionaron Markdown, Python, SQL, JSON, YAML y manifests CSV/TSV cuando eran evidencia o investigación.

```text
SAP_ACCESSED=NO
SAP_ACCESS_PURPOSE=NONE
SAP_WRITE_COUNT=0
SOURCE_EVIDENCE_MODIFIED=0
```

Este gate no ejecuta conectores SAP y no escribe Data Root, Legacy Root ni Private Root.

## D. Gates/investigaciones encontrados

El inventario completo, con `gate_id,title,domain,status,date_if_known,source_document,
source_code,evidence_path,sap_access,read_only,tables,business_question,main_result,
confidence`, está en `sap_gates_inventory.csv`. Los estados explícitos encontrados son:

```text
{dict(sorted(status_counts.items()))}
```

Muestras de gates principales y su alcance:

{_md_table(["Gate", "Estado", "Dominio", "Fuente"], ((r["gate_id"], r["status"], r["domain"], r["source_document"]) for r in gates if r["status"] in {"PASS", "DEGRADED", "FAIL"}))}

Los estados históricos se conservan: un `FAIL` previo no se transforma en PASS por la
existencia de un PASS posterior; la vigencia se lee en el documento fechado y en el
`STATUS_ACTUAL.md`.

## E. Mapa funcional SAP

| Dominio | Conocimiento ya validado | Núcleo SAP | Estado |
|---|---|---|---|
| Ventas / documentos | factura, NC, proforma, pedido, entrega, cancelación, canal | OINV/INV1, ORIN/RIN1, OQUT/QUT1, ORDR/RDR1, ODLN/DLN1 | CONFIRMED con temporalidad parcial |
| Crédito / cobranzas | saldo as-of, vencido, límite, excepción, aging, reconciliación | OCRD, OINV, ORIN, ORCT, ITR1/OITR, OADM | CONFIRMED; autorizaciones históricas UNKNOWN |
| Compras | solicitud, PO, AP, recepción, devolución, proveedor, tipo, lead time | OPRQ/PRQ1, OPOR/POR1, OPCH/PCH1, OPDN/PDN1, ORPD/RPD1 | CONFIRMED |
| Stock / transferencias | stock actual, ledger, roles de almacén, transferencia contable | OITW, OINM, OWHS, OWTR/WTR1 | CONFIRMED; físico no demostrado |
| Producción / BOM | receta histórica, consumo, output, reconciliación, dependencia | OITT/ITT1, OWOR/WOR1, OIGE/IGE1, OIGN/IGN1 | CONFIRMED con links parciales |
| MRP / forecast | parámetros, cobertura, forecasts observados, seasonality | OITM/OITW, OFCT/FCT1 | CONFIGURED/OBSERVED; operación UNKNOWN |
| Usuarios / permisos | usuarios, grupos, capabilities, actividad, atribución de canal | OUSR/USR3/UGR1/OUGR/USR5/OHEM/OSLP/OUPT | CONFIRMED current-only |
| Finanzas / tesorería | GL, AR/AP, cash, bancos, depósitos, deuda, resultado | OACT/OJDT/JDT1, ORCT/OVPM/ODPS, OBNK | CONFIRMED/PARTIAL |
| RRHH / WHT | maestro empleado y costo GL; configuración WHT | OHEM/OACT/JDT1, OWHT/PCH5/PCH6/VPM6 | DEGRADED |

## F. Catálogo de tablas

El catálogo completo y sus ocho campos contractuales está en `sap_tables_inventory.csv`
(**{len(TABLE_SPECS)} objetos**). Se conservan campos de configuración y UDF relevantes
sin confundirlos con una prueba de uso operacional. Entre los UDT/UDF externos detectados
se preservan como objetos auxiliares en los reportes: `@SO1_01LOGAUTORIZA`,
`@SO1_01VENCREVENC`, `@SO1_01COMPRA*` y `@SO1_01SUGERENCOMPRA`, además de
`U_TIPOCOMPRA`, `U_ORIGIN`, `U_SO1_01RETAILONE` y `U_LOTE`.

{_md_table(["Tabla", "Dominio", "Propósito", "Clave candidata", "Confianza"], ((r[0], r[1], r[2], r[3], r[7]) for r in TABLE_SPECS))}

## G. Relaciones confirmadas y no confirmadas

No se elevó un join a `CONFIRMED` solo por ser estándar SAP: cada relación confirmada
abajo tiene evidencia Telchi, SQL, test o reporte inequívoco. `LIKELY/POSSIBLE` queda
separada para el siguiente gate.

{_md_table(["Izquierda", "Clave", "Derecha", "Clave", "Tipo", "Significado", "Confianza"], relationship_rows)}

La cardinalidad anti-fanout es parte del conocimiento: en usuarios y documentos 1:N se
agrega antes de cruzar importes; el caso `OINV→OINM` es multi-línea y no debe sumarse por
join ingenuo.

## H. Reglas de negocio validadas

Las reglas centrales, su evidencia y confianza están en `sap_business_rules_inventory.csv`.
Resumen de las reglas que no deben perderse:

1. **Settlement:** `OITR/ITR1` es autoridad de liquidación; `RCT2` es referencia de aplicación.
2. **As-of credit:** saldo, vencimiento y cobros se evalúan con fecha de reconciliación y estado de documentos al corte; no con `PaidToDate` aislado.
3. **Purchases:** `BaseEntry→DocEntry` es el link canónico; el flujo observado es predominantemente invoice-first.
4. **Inventory:** `OnHand`, `IsCommited` y `OnOrder` son capas semánticas distintas; no se suma `OITW.OnOrder` con PO abierta sin reconciliación.
5. **Production:** `WOR1` conserva receta de la orden; `IGE1` es consumo real y `IGN1` output real; `CmpltQty` no reemplaza output.
6. **Transfers:** `FromWhsCod→WhsCode` conserva el evento contable TT67, no prueba tránsito físico.
7. **MRP:** `CONFIGURED`, `VALIDATED` y `OBSERVED` deben permanecer separados.
8. **Users:** `OJDT.UserSign` suele ser usuario de transacción origen; una fila USR5 no equivale a una operación.
9. **Finance/WHT/HR:** configuración, movimiento GL y proceso externo son conceptos distintos; no se afirma nómina detallada ni WHT activo sin evidencia.

## I. Métricas baseline

Estas métricas son **VALIDATION BASELINE**, no diseño ni carga propuesta. Cada fila tiene
universo/filtros, tablas, gate y reproducibilidad en `sap_validated_metrics.csv`.

{_md_table(["ID", "Métrica", "Dominio", "Valor", "Período", "Reproducible"], ((r[0], r[1], r[2], r[3], r[4], r[8]) for r in METRICS))}

## J. Universos especiales

- Gate de crédito: ventanas as-of explícitas; 287 es baseline operativo revalidado y 2,318 es el universo exacto ampliado, no intercambiables.
- Productos `ItemCode LIKE 'L%'`: usado en reposición/producción como universo de análisis, no regla universal de todos los gates.
- Producción: `Type='S'`, `BaseType=202`, y separación de `Released`/`Closed` según evidencia observada.
- Compras: `U_TIPOCOMPRA in {{LF,LP,IMP,SERV,SAA}}`; `OpenQty>0` para ordenado no recibido.
- Stock: activo/cancelado, almacén por rol, y separación `OnHand-IsCommited` de `OnOrder`.
- Usuarios: activos/bloqueados, superuser, técnico vs persona; `USR5` agregado por usuario/evento.
- Finanzas: `BS` y `USD` no se compensan; P&L excluye asientos de apertura/cierre según contrato.

## K. Correspondencia HISTÓRICO ↔ SAP

Gate 1 se usó literalmente y no se reinterpretó. El detalle está en
`sap_historical_mapping.csv` (**{len(MAPPINGS)} correspondencias**).

{_md_table(["Familia histórica", "Fuente SAP candidata", "Matching", "Grano/diferencia", "Confianza"], ((r[1], r[2], r[3], r[4], r[7]) for r in MAPPINGS))}

Conclusión: `saleSB1Product`, `movProductSB1`, `ncB1Product`, `productSB1`, `clientSB1`,
`owhsSB1`, `wareHouseSB1`, `paymentB1` y `reconB1` tienen candidatos plausibles y
artefactos compatibles, pero solo algunos campos/relaciones son `LIKELY`; no se declara
`CONFIRMED` sin reconciliación de cobertura, grano, fechas y lineage.

## L. Conocimiento no materializado / gaps

La tabla completa, separada por clase solicitada, está en `sap_data_gaps.csv` (**{len(GAPS)} gaps**).

{_md_table(["ID", "Clase", "Conocimiento", "Gap", "Prioridad"], GAPS)}

En particular, SAP actual aporta conocimiento que no aparece completo en el histórico:
BOM/órdenes/consumos/output, stock actual/OINM, transferencias documentales, MRP/forecast,
usuarios/permisos actuales, GL/AP/AR/tesorería y deuda. En sentido inverso, el histórico
aporta familias legacy como `productTracking`, `purchaseExpense`, `productTransform`,
`cash` y `cuentasxCobrar` cuya semántica SAP equivalente es parcial o UNKNOWN.

## M. Candidate Data Products

Son límites semánticos candidatos; no son nombres definitivos de Parquet, particiones,
capas raw/staging/atomic/business/decision ni layout físico.

{_md_table(["Candidato", "Dominio", "Conocimiento", "Estado", "security_domain", "Sensibilidad"], PRODUCTS)}

## N. Seguridad futura

En esta fase se consideró `administrator/administrators`, scope ALL. No se implementaron
permisos. La matriz futura está en `sap_security_domains.csv` y etiqueta dominios, alcance
organizacional candidato y campos sensibles.

{_md_table(["security_domain", "Dominio", "Campos sensibles", "Row scope candidato", "Fase"], SECURITY)}

Invariante futura: **SECURITY BEFORE RETRIEVAL**; debe combinar RBAC, scope organizacional,
filtros de fila, políticas de columna y políticas de métrica.

## O. Tracking de lineage

La materia prima queda en los CSV y en cada fuente primaria: reporte, script/SQL, test y
evidencia externa. El contrato aún no está cerrado. Cada métrica y regla apunta a tablas,
gate y documento; cada mapping conserva matching, grano, cobertura y diferencia semántica.
No existe todavía un `source_query_or_code` universal ni watermark de extracción para los
Parquet legacy; por eso `LINEAGE_UNKNOWN` es un gap material y no se oculta.

## P. Limitaciones y decisión del gate

```text
HISTORICAL_INVENTORY_USED=YES
SAP_ACCESSED=NO
SAP_ACCESS_PURPOSE=NONE
SAP_WRITE_COUNT=0
SAP_GATES_FOUND={len(gates)}
SAP_TABLES_CATALOGUED={len(TABLE_SPECS)}
SAP_RELATIONSHIPS_CATALOGUED={len(relationship_rows)}
SAP_BUSINESS_RULES_CATALOGUED={len(rule_rows)}
SAP_METRICS_BASELINED={len(metric_rows)}
HISTORICAL_SAP_MAPPINGS={len(mapping_rows)}
UNRESOLVED_GAPS={len(gap_rows)}
SOURCE_EVIDENCE_MODIFIED=0
PRODUCTION_PARQUETS_CREATED=0
DATALAKE_PHYSICAL_DESIGN_CREATED=0
```

`TELCHI_SAP_KNOWLEDGE_INVENTORY_V1_DEGRADED`

## Q. Recomendación para el siguiente gate

No implementarla en este gate. El siguiente gate debe aprobar, usando estos catálogos como
fuente:

```text
CANONICAL BUSINESS MODEL
+ LINEAGE CONTRACT
+ SNAPSHOT POLICY
+ DATA PRODUCT BOUNDARIES
```

Debe resolver primero el grano de `movProductSB1`/`saleSB1Product`, la política as-of y
los snapshots acumulativos, equivalencias legacy↔SAP, seguridad antes de retrieval y qué
baselines serán regresiones. Recién después corresponde diseñar formatos/particiones y
producir datasets físicos.

## R. Archivos reproducibles

- `validation/sap_knowledge_inventory_v1/inventory.py`
- `validation/sap_knowledge_inventory_v1/sap_gates_inventory.csv`
- `validation/sap_knowledge_inventory_v1/sap_tables_inventory.csv`
- `validation/sap_knowledge_inventory_v1/sap_relationships_inventory.csv`
- `validation/sap_knowledge_inventory_v1/sap_business_rules_inventory.csv`
- `validation/sap_knowledge_inventory_v1/sap_validated_metrics.csv`
- `validation/sap_knowledge_inventory_v1/sap_historical_mapping.csv`
- `validation/sap_knowledge_inventory_v1/sap_data_gaps.csv`
- `validation/sap_knowledge_inventory_v1/sap_candidate_data_products.csv`
- `validation/sap_knowledge_inventory_v1/sap_security_domains.csv`

El runner solo genera esos inventarios pequeños, un resumen JSON y este informe. No crea Parquet
productivos, no mueve históricos y no accede SAP.
"""


def build() -> dict[str, int]:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    gates = _gate_rows()
    manifest = EVIDENCE_ROOT / "EVIDENCE_MANIFEST.tsv"
    if manifest.exists():
        evidence_count = max(0, sum(1 for _ in manifest.open(encoding="utf-8", errors="ignore")) - 1)
    else:
        # Do not walk a potentially large evidence root during the normal gate.
        evidence_count = 0
    _write_csv("sap_gates_inventory.csv", list(gates[0]), gates)
    _write_csv("sap_tables_inventory.csv", ["table_name", "business_domain", "purpose", "primary_or_candidate_key", "important_columns", "used_in_gates", "join_targets", "confidence"], TABLE_SPECS)
    _write_csv("sap_relationships_inventory.csv", ["left_table", "left_key", "right_table", "right_key", "relationship_type", "business_meaning", "validated_by", "confidence"], RELATIONSHIPS)
    _write_csv("sap_business_rules_inventory.csv", ["rule_id", "domain", "business_question", "tables", "rule", "gate", "confidence"], RULES)
    _write_csv("sap_validated_metrics.csv", ["metric_id", "metric_name", "domain", "value", "period", "universe_filters", "source_tables", "gate_evidence", "reproducible"], METRICS)
    _write_csv("sap_historical_mapping.csv", ["mapping_id", "historical_family", "sap_source", "matching_fields", "granularity_comparison", "coverage_comparison", "semantic_differences", "confidence", "evidence"], MAPPINGS)
    _write_csv("sap_data_gaps.csv", ["gap_id", "gap_class", "knowledge", "gap", "next_action", "priority"], GAPS)
    _write_csv("sap_candidate_data_products.csv", ["candidate_data_product", "domain", "knowledge_boundary", "state", "security_domain", "sensitive_fields"], PRODUCTS)
    _write_csv("sap_security_domains.csv", ["security_domain", "domain", "sensitive_fields", "organizational_scope_candidate", "gate_scope"], SECURITY)
    REPORT.write_text(_report(gates, evidence_count), encoding="utf-8")
    summary = {
        "gate": "TELCHI_SAP_KNOWLEDGE_INVENTORY_V1_DEGRADED",
        "historical_inventory_used": True,
        "sap_accessed": False,
        "sap_access_purpose": "NONE",
        "sap_write_count": 0,
        "sap_gates_found": len(gates),
        "sap_tables_catalogued": len(TABLE_SPECS),
        "sap_relationships_catalogued": len(RELATIONSHIPS),
        "sap_business_rules_catalogued": len(RULES),
        "sap_metrics_baselined": len(METRICS),
        "historical_sap_mappings": len(MAPPINGS),
        "unresolved_gaps": len(GAPS),
        "source_evidence_modified": 0,
        "production_parquets_created": 0,
        "datalake_physical_design_created": 0,
    }
    (OUTPUT / "sap_knowledge_inventory_v1_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return {k: v for k, v in summary.items() if isinstance(v, int)}


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
