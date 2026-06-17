from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Canonical multilingual semantic extraction
#
# Each canonical value maps to a compiled regex that matches terms in
# Spanish, English, and Hebrew. Extraction functions return canonical values
# (not the original words), producing a language-independent semantic memory.
# ---------------------------------------------------------------------------


# ── Channels ──────────────────────────────────────────────────────────────

def _word(value: str) -> re.Pattern:
    """Compile a case-insensitive pattern with word boundaries.
    For ASCII-only; Hebrew is matched without \\b."""
    return re.compile(r"\b" + value + r"\b", re.IGNORECASE)


HEB_CHARS = r"אבגדהוזחטיכלמנסעפצקרשתךםןףץ"


def _word_or_any(value: str, hebrew: str) -> re.Pattern:
    """Match ASCII (with \\b) or Hebrew (substring, no \\b)."""
    return re.compile(
        r"(?:\b" + value + r"\b)|(?:" + hebrew + r")",
        re.IGNORECASE,
    )


CHANNEL_PATTERNS: dict[str, re.Pattern] = {
    "whatsapp": _word_or_any("whatsapp", "וואטסאפ"),
    "gmail": _word_or_any("gmail", "ג׳ימייל"),
    "email": re.compile(
        r"(?:\b(?:email|e-mail|correo|correo electr[oó]nico)\b)"
        r"|(?:דואר\s*אלקטרוני|אימייל)",
        re.IGNORECASE,
    ),
    "telegram": _word("telegram"),
    "facebook": _word("facebook"),
    "instagram": _word("instagram"),
    "web": re.compile(
        r"(?:\b(?:web|sitio|p[aá]gina|website|intranet)\b)"
        r"|(?:אתר|אינטרנט)",
        re.IGNORECASE,
    ),
    "phone": re.compile(
        r"(?:\b(?:tel[eé]fono|telefono|phone)\b)|(?:טלפון)",
        re.IGNORECASE,
    ),
    "chat": _word("chat"),
}

# ── Systems and data sources ──────────────────────────────────────────────

SYSTEM_PATTERNS: dict[str, re.Pattern] = {
    "erp": _word("erp"),
    "crm": _word("crm"),
    "spreadsheet": re.compile(
        r"(?:\b(?:planilla|hoja\s*de\s*c[aá]lculo|excel|sheet|spreadsheet|"
        r"google\s*sheet)\b)"
        r"|(?:גיליון|אקסל)",
        re.IGNORECASE,
    ),
    "database": re.compile(
        r"(?:\b(?:base\s+de\s+datos|database|bd)\b)"
        r"|(?:מסד\s+נתונים)",
        re.IGNORECASE,
    ),
    "inventory_system": re.compile(
        r"(?:\b(?:sistema\s+de\s+stock|inventory\s+system)\b)"
        r"|(?:מערכת\s+מלאי)",
        re.IGNORECASE,
    ),
    "closed_windows_application": re.compile(
        r"(?:\b(?:programa\s+cerrado\s+de\s+windows|"
        r"closed\s+windows\s+application)\b)"
        r"|(?:תוכנת\s+windows\s+סגורה)",
        re.IGNORECASE,
    ),
    "proprietary_system": re.compile(
        r"(?:\b(?:software\s+propietario|proprietary\s+(?:software|system))\b)"
        r"|(?:תוכנה\s+קניינית)",
        re.IGNORECASE,
    ),
}

# ── Business entities that users may reference ────────────────────────────

ENTITY_PATTERNS: dict[str, re.Pattern] = {
    "inventory": re.compile(
        r"(?:\b(?:stock|inventario|inventory)\b)|(?:מלאי)",
        re.IGNORECASE,
    ),
    "prices": re.compile(
        r"(?:\b(?:precios?|prices?|precio|price|pricing)\b)|(?:מחירים?|מחיר)",
        re.IGNORECASE,
    ),
    "customers": re.compile(
        r"(?:\b(?:clientes?|customers?)\b)|(?:לקוחות?)",
        re.IGNORECASE,
    ),
    "sales_inquiries": re.compile(
        r"(?:\b(?:consultas?\s+de\s+venta|ventas?|sales\s+inquir(?:y|ies))\b)"
        r"|(?:פניות?\s+מכירה)",
        re.IGNORECASE,
    ),
    "discounts": re.compile(
        r"(?:\b(?:descuentos?|discounts?)\b)|(?:הנחות?)",
        re.IGNORECASE,
    ),
    "claims": re.compile(
        r"(?:\b(?:reclamos?|claims?)\b)|(?:תביעות?)",
        re.IGNORECASE,
    ),
    "orders": re.compile(
        r"(?:\b(?:pedidos?|orders?)\b)|(?:הזמנות?)",
        re.IGNORECASE,
    ),
    "documents": re.compile(
        r"(?:\b(?:documentos?|documents?)\b)|(?:מסמכים?)",
        re.IGNORECASE,
    ),
}

# ── Approval / human review ───────────────────────────────────────────────

_HEB_APPROVAL = r"אישור\s+מנהל|בדיקה\s+אנושית"

APPROVAL_CONDITIONAL_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"(?:\b(?:"
        r"las\s+respuestas\s+comunes\s+(?:pueden\s+)?salir\s+(?:solas|autom[aá]ticamente)"
        r"|"
        r"common\s+(?:replies|answers)\s+(?:\w+\s+){0,4}automatic"
        r"|"
        r"תשובות\s+רגילות\s+יכולות\s+(?:לצאת\s+)?באופן\s+אוטומטי"
        r")\b)"
        r".*?"
        r"(?:(?:\b(?:pero|but)\b)|(?:אבל))"
        r".*?"
        r"(?:(?:\b(?:descuentos?|discounts?)\b)|(?:הנחות?))"
        r".*?"
        r"(?:(?:\b(?:aprobaci[oó]n|revisa|manager\s+approval|human\s+review)\b)"
        r"|(?:" + _HEB_APPROVAL + r"))",
        re.IGNORECASE | re.DOTALL,
    ),
]

APPROVAL_REQUIRED_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"(?:\b(?:"
        r"aprobaci[oó]n|supervisor|revisa|revisi[oó]n|"
        r"autorizaci[oó]n|"       # autorización with accent
        r"humano|persona\s+revisa|validaci[oó]n|"
        r"manager\s+approval|human\s+review|requires?\s+approval|needs?\s+review"
        r")\b)"
        r"|(?:" + _HEB_APPROVAL + r")"
        r"|(?:נדרשת?\s+בדיקה)",
        re.IGNORECASE,
    ),
]

# ── Volume / frequency ────────────────────────────────────────────────────

VOLUME_PATTERNS: list[re.Pattern] = [
    # "80 por día", "80 per day", "80 ביום", "100 consultas diarias", "60 al mes"
    # Also: "around 80 per day" (leading word before number)
    re.compile(
        r"(?:\w+\s+)?"
        r"(?P<value>\d+[\.\d]*)\s*"
        r"(?P<unit>consultas?|mensajes?|inquir(?:y|ies)|"
        r"units?|clientes?|leads?|llamadas?|calls?|correos?|emails?|"
        r"פניות?)?\s*"
        r"(?:(?:al|por|per|ל)\s+|(?:\s*ב)?\s*)?"
        r"(?P<period>"
        r"diarias?|diarios?|"
        r"d[ií]a(?:s)?|dia(?:s)?|"
        r"dail(?:y)?|day|"
        r"semana(?:s)?|week(?:ly)?|"
        r"mes(?:es)?|month(?:ly)?|"
        r"a[ñn]o(?:s)?|year(?:ly)?|"
        r"(?:ב)?(?:יום|שבוע|חודש|שנה)"
        r")",
        re.IGNORECASE,
    ),
]

# ── Correction indicators (multilingual) ─────────────────────────────────

CORRECTION_PHRASES: list[re.Pattern] = [
    re.compile(r"\b(en\s+realidad|mejor\s+dicho|rectifico|correcci[oó]n)", re.IGNORECASE),
    re.compile(r"\b(actually|correction|i\s+meant|let\s+me\s+correct)", re.IGNORECASE),
    re.compile(r"\b(בעצם|למעשה|אני\s+מתקן)", re.IGNORECASE),
]

# ── Helper: general problem / outcome (keep as-is for backward compat) ───

GENERAL_PROBLEM_PATTERNS = re.compile(
    r"\b(problem|pierd|tard|error|manual|desorden|lento|d[ií]ficil|complej|"
    r"cuest|sobrecarga|desorganiz|descontrol|ca[oó]tico|ineficiente|"
    r"difficult|complex|overload|chaotic|inefficient)\b",
    re.IGNORECASE,
)

GENERAL_OUTCOME_PATTERNS = re.compile(
    r"\b(quer[eé]|necesit|automatiz|orden|mejor|aceler|respond|optimiz|"
    r"agiliz|simplific|digitaliz|automate|improve|optimize|digitize|"
    r"simplify|respond|רוצה|צריך|צריכה|אוטומטי|לשפר|לייעל)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Extraction functions
# ---------------------------------------------------------------------------


def extract_channels(message: str) -> list[str]:
    found: list[str] = []
    for canonical, pattern in CHANNEL_PATTERNS.items():
        if pattern.search(message):
            found.append(canonical)
    return found


def extract_systems(message: str) -> list[str]:
    found: list[str] = []
    for canonical, pattern in SYSTEM_PATTERNS.items():
        if pattern.search(message):
            found.append(canonical)
    return found


def extract_entities(message: str) -> list[str]:
    found: list[str] = []
    for canonical, pattern in ENTITY_PATTERNS.items():
        if pattern.search(message):
            found.append(canonical)
    return found


def extract_approval(message: str) -> str | None:
    """Returns 'conditional', 'required', or None.
    Conditional is checked first because it contains approval terms
    within a broader conditional pattern."""
    for pattern in APPROVAL_CONDITIONAL_PATTERNS:
        if pattern.search(message):
            return "conditional"
    for pattern in APPROVAL_REQUIRED_PATTERNS:
        if pattern.search(message):
            return "required"
    return None


def extract_volume(message: str) -> dict | None:
    """Returns {'value': N, 'unit': str|None, 'period': str} or None."""
    for pattern in VOLUME_PATTERNS:
        m = pattern.search(message)
        if m:
            try:
                val = float(m.group("value"))
            except (ValueError, IndexError):
                continue
            period = m.group("period") or "day"
            period = period.lower()[:20]
            # Normalize plural only for long words (keep "mes" intact)
            if len(period) > 3 and period.endswith("s"):
                period = period[:-1]
            unit = m.group("unit")
            unit = unit.lower().rstrip("s") if unit else None
            return {
                "value": int(val) if val == int(val) else val,
                "unit": unit,
                "period": period,
            }
    return None


def is_correction(message: str) -> bool:
    for pattern in CORRECTION_PHRASES:
        if pattern.search(message):
            return True
    return False


def is_business_context(message: str) -> str | None:
    m = re.search(
        r"(?:mi\s+)?(negocio|empresa|comercio|tienda|taller|local|"
        r"profesi[oó]n|business|company|store|shop|עסק|חברה|חנות)\s+"
        r"(es|de|se\s+dedica|vende|vendo|ofrece|trabajo|is|sells|"
        r"that\s+sells|של|הוא|מוכר|עוסק)",
        message,
        re.IGNORECASE,
    )
    return message if m else None
