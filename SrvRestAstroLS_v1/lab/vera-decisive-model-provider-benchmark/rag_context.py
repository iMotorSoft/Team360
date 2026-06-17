"""Contexto RAG estatico para el benchmark decisivo de modelos Vera.

Modo: static_deterministic
Razon: pymilvus no esta instalido en el entorno de ejecucion.
Todos los modelos reciben exactamente los mismos chunks.
No se usa LiteLLM.
"""

RAG_CHUNKS = [
    {
        "source": "knowledge_base/team360_capabilities",
        "content": (
            "Team360 es una plataforma de automatizacion conversacional multicanal. "
            "Soporta integracion con WhatsApp Business API, Gmail/Google Workspace, "
            "web chat y redes sociales. Puede clasificar consultas, responder "
            "automaticamente mensajes comunes y escalar casos complejos a humanos."
        ),
        "score": 0.95,
    },
    {
        "source": "knowledge_base/automation_approaches",
        "content": (
            "Cuando el cliente usa un sistema cerrado (software contable, ERP sin API, "
            "programa de escritorio en Windows), la automatizacion puede requerir: "
            "1) integracion por RPA (Robot Process Automation) que interactua con la interfaz, "
            "2) exportacion/importacion de archivos intermedios, "
            "3) bridge de base de datos si el programa usa una DB estandar accesible. "
            "No se debe prometer integracion directa sin validar antes."
        ),
        "score": 0.92,
    },
    {
        "source": "knowledge_base/document_types_israel",
        "content": (
            "En Israel, los documentos comerciales comunes incluyen: "
            "Kabala (קבלה) - recibo de pago, Cheshbonit (חשבונית) - factura, "
            "Kabala Mashe (קבלה מס) - recibo fiscal. "
            "Estos documentos deben cumplir con requisitos fiscales de la Rashaam Hakesafim (Autoridad Tributaria de Israel). "
            "La automatizacion de emision requiere que el sistema genere el formato correcto."
        ),
        "score": 0.88,
    },
    {
        "source": "knowledge_base/smb_patterns",
        "content": (
            "PyMEs con 100-500 productos y 20-50 consultas diarias suelen beneficiarse de "
            "automatizacion parcial: respuestas automaticas a preguntas frecuentes "
            "(horarios, precios publicos, disponibilidad basica) y escalamiento a humano "
            "para descuentos, condiciones especiales, reclamos o personalizacion. "
            "La separacion entre stock y precios en fuentes distintas es comun y "
            "gestionable con integracion liviana."
        ),
        "score": 0.90,
    },
    {
        "source": "knowledge_base/feasibility_framework",
        "content": (
            "Marco de factibilidad: "
            "1) Canales de entrada disponibles (WhatsApp, Gmail, web) -> alta factibilidad. "
            "2) Fuente de datos de productos (sistema, planilla, API) -> factibilidad media/alta. "
            "3) Sistema de emision documentos (ERP, software escritorio, manual) -> requiere validacion. "
            "4) Reglas de negocio (descuentos, excepciones aprobacion) -> factibles con configuracion. "
            "Separar siempre la factibilidad tecnica (se puede hacer) de la disponibilidad "
            "comercial (esta disponible en Team360 hoy)."
        ),
        "score": 0.93,
    },
    {
        "source": "knowledge_base/security_boundaries",
        "content": (
            "Team360 no solicita ni almacena credenciales de sistemas del cliente. "
            "No promete evadir MFA, controles anti-bot, firmas digitales ni restricciones "
            "de seguridad nativas del software del cliente. "
            "Las integraciones con sistemas cerrados deben evaluarse caso por caso "
            "y documentar los limites de seguridad."
        ),
        "score": 0.96,
    },
]

RETRIEVAL_MODE = "static_deterministic"
RETRIEVAL_NOTE = (
    "Modo estatico: todos los modelos reciben los mismos chunks predefinidos. "
    "pymilvus no esta disponible en el entorno Python actual. "
    "No se usa LiteLLM. No se usan embeddings. "
    "Los chunks representan conocimiento relevante para el caso de evaluacion."
)

RETRIEVAL_QUERY_CANONICAL = (
    "automatizacion consultas WhatsApp Gmail repuestos Israel Kabala programa contable "
    "Windows stock precios planilla descuentos aprobacion"
)
