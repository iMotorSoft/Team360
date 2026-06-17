"""Caso decisivo de evaluacion unico para comparacion de modelos Vera.

Una pequena empresa vende repuestos industriales en Israel.
Recibe consultas por WhatsApp y Gmail.
Usa un programa contable cerrado en Windows para emitir Kabala (recibo).
Stock en sistema, precios en planilla.
Descuentos especiales requieren aprobacion humana.
"""

CONVERSATION_TURNS = [
    {
        "user_message": "quiero automatizar las consultas que me llegan",
        "action": "reflect_and_ask",
    },
    {
        "user_message": "sometimes llegan por WhatsApp y otros por Gmail, vendemos repuestos industriales",
        "action": "reflect_and_ask",
    },
    {
        "user_message": "tengo el stock y los precios en una planilla de Excel, unos 200 productos",
        "action": "reflect_and_ask",
    },
    {
        "user_message": "dame ya el diagnostico, quiero saber si se puede hacer",
        "action": "reflect_and_ask",
    },
    {
        "user_message": "en realidad el stock esta en el sistema, los precios si estan en la planilla",
        "action": "reflect_and_ask",
    },
    {
        "user_message": "uso un programa contable cerrado en Windows, ahi hago la kabala קבלה cuando vendemos",
        "action": "reflect_and_ask",
    },
    {
        "user_message": "las respuestas comunes sin aprobacion pueden ir solas, descuentos especiales los reviso yo antes",
        "action": "reflect_and_ask",
    },
    {
        "user_message": "con todo esto dame el diagnostico y que haras primero",
        "action": "diagnose",
    },
]

SYSTEM_PROMPT = """Sos Vera, diagnosticadora de automatizaciones de Team360.
Conversas con usuarios no tecnicos. Respondes en espanol natural.

Durante la entrevista:
- Una sola pregunta principal por turno.
- Respuestas breves.
- No repetir preguntas.
- No convertir la conversacion en formulario.
- Demostrar comprension sin repetir todo.
- No prometer integraciones no validadas.

Cuando haya informacion suficiente:
- Entregar diagnostico inicial profesional.
- Resumir proceso.
- Identificar oportunidad.
- Mencionar sistemas e integracion.
- Senalar riesgos.
- Proponer proximo paso.

Distinguir factibilidad tecnica de disponibilidad comercial.
No activar lead capture, WhatsApp handoff, diagnostic_code ni Step-to-Action.
No inventar pricing, SLA o ROI.

Cierre del diagnostico:
- Cuando el usuario solicite el diagnostico explicitamente, ese es el momento de cerrar.
- No hacer mas preguntas salvo bloqueo critico real.
- La respuesta final debe: resumir el proceso, reconocer los canales, identificar sistemas,
  recomendar automatizacion o semi-automatizacion, mencionar necesidad de validar integracion,
  no prometer implementacion cerrada y dar un proximo paso concreto."""

ACTION_INSTRUCTIONS = {
    "reflect_and_ask": (
        "Accion de este turno: continuar el diagnostico. "
        "No generes el diagnostico final. "
        "Responde brevemente y haz una sola pregunta principal que avance el caso."
    ),
    "diagnose": (
        "Accion de este turno: generar ahora el diagnostico inicial completo. "
        "No hagas nuevas preguntas salvo que exista un bloqueo critico real."
    ),
}

GOLDEN_ANSWER_SEMANTIC = {
    "process_summary": True,
    "channels": {"whatsapp": True, "gmail": True, "web": False},
    "system_windows_closed": True,
    "commercial_documents_kabala": True,
    "stock_in_system": True,
    "prices_in_spreadsheet": True,
    "responses_auto_without_approval": True,
    "discounts_require_human_approval": True,
    "good_initial_feasibility": True,
    "integration_limited_by_closed_software": True,
    "mentions_rpa_or_bridge_option": True,
    "no_credentials_request": True,
    "no_security_bypass_promise": True,
    "risk_flags": True,
    "assumptions_declared": True,
    "concrete_next_step": True,
    "separates_feasibility_from_commercial": True,
}
