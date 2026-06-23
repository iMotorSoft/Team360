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
        r"(?:\b(?:email|e-mail|correo|correo electr[oó]nico|mail|mails|emails?)\b)"
        r"|(?:דואר\s*אלקטרוני|אימייל)",
        re.IGNORECASE,
    ),
    "telegram": _word("telegram"),
    "facebook": _word("facebook"),
    "instagram": _word("instagram"),
    "tiktok": _word("tiktok"),
    "meta": _word("meta"),
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
    "kommo": _word("kommo"),
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
    "custom_system": re.compile(
        r"(?:\b(?:sistema\s+propio|propio)\b)",
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

_HEB_APPROVAL = r"אישור(?:\s+מנהל)?|בדיקה\s+אנושית"

APPROVAL_CONDITIONAL_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"(?:\b(?:"
        r"las\s+respuestas\s+comunes\s+(?:pueden\s+)?sal(?:ir|en)\s+(?:solas|autom[aá]ticamente)"
        r"|"
        r"common\s+(?:replies|answers)\s+(?:\w+\s+){0,4}automatic"
        r")"
        r"|(?:"
        r"תשובות\s+רגילות\s+(?:יכולות\s+(?:לצאת\s+)?)?(?:באופן\s+)?אוטומטיות?"
        r"))"
        r".*?"
        r"(?:(?:\b(?:pero|but)\b)|(?:אבל))"
        r".*?"
        r"(?:(?:\b(?:descuentos?|discounts?)\b)|(?:הנחות?))"
        r".*?"
        r"(?:(?:\b(?:aprobaci[oó]n|revisa|manager\s+approval|human\s+review|requires?\s+approval)\b)"
        r"|(?:" + _HEB_APPROVAL + r"))",
        re.IGNORECASE | re.DOTALL,
    ),
]

APPROVAL_REQUIRED_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"(?:\b(?:"
        r"aprobaci[oó]n|aprobad[oó]|"
        r"supervisor|revisa|revisi[oó]n|"
        r"autorizaci[oó]n|"
        r"humano|persona\s+revisa|validaci[oó]n|"
        r"manager\s+approval|human\s+review|requires?\s+approval|needs?\s+review|"
        r"must\s+be\s+approved|requires?\s+human\s+approval"
        r")\b)"
        r"|(?:" + _HEB_APPROVAL + r")"
        r"|(?:"
        r"נדרשת?\s+בדיקה|"
        r"דורש(?:ות)?\s+אישור|"
        r"דרושה?\s+בדיקה"
        r")",
        re.IGNORECASE,
    ),
]

APPROVAL_NOT_REQUIRED_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"(?:\b(?:"
        r"no\s+requiere\s+aprobaci[oó]n|"
        r"no\s+necesita\s+revisi[oó]n|"
        r"no\s+human\s+approval|"
        r"does\s+not\s+need|"
        r"does\s+not\s+require|"
        r"not\s+required"
        r")\b)"
        r"|(?:"
        r"לא\s+נדרש|"
        r"לא\s+צריך"
        r")",
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
        r"pedidos?|orders?|הזמנות?|פניות?)?\s*"
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
    re.compile(r"\b(en\s+realidad|mejor\s+dicho|rectifico|correcci[oó]n|ya\s+no)", re.IGNORECASE),
    re.compile(r"\b(actually|correction|i\s+meant|let\s+me\s+correct|no\s+longer)", re.IGNORECASE),
    re.compile(r"\b(בעצם|למעשה|אני\s+מתקן|כבר\s+לא)", re.IGNORECASE),
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


NEGATION_PREFIX = re.compile(
    r"(?:\b(?:no\s+(?:usamos|tenemos|recibimos|contamos|manejamos|trabajamos|ocupamos|es|son|era)"
    r"|nunca|ya\s+no|todav[íi]a\s+no|a[úu]n\s+no|sin\s+(?:usar|tener|contar|un|una)\b"
    r"|no\s+(?:se\s+)?(?:responde|atiende|gestiona|maneja|usa|tiene|recibe)"
    r")\b)",
    re.IGNORECASE,
)

NON_ASSERTIVE_PREFIX = re.compile(
    r"(?:\b(?:tal\s+vez|quiz[aá]s|podr[íi]a|si\s+tuvi[ée]ramos|si\s+us[aá]ramos"
    r"|por\s+ejemplo|supongamos|digamos|imagin[aá])\b)",
    re.IGNORECASE,
)

TEMPORAL_PAST = re.compile(
    r"(?:\b(?:antes|antiguamente|sol[íi]amos|sol[íi]a|us[aá]bamos|us[aá]ba|dije"
    r"|el\s+a[ñn]o\s+pasado|hace\s+tiempo)\b)",
    re.IGNORECASE,
)

TEMPORAL_FUTURE = re.compile(
    r"(?:\b(?:en\s+el\s+futuro|m[aá]s\s+adelante|pr[oó]ximamente|vamos\s+a"
    r"|queremos|pensamos|planeamos|implementaremos|migraremos)\b)",
    re.IGNORECASE,
)

ALL_PATTERNS: dict[str, re.Pattern] = {}
ALL_PATTERNS.update(CHANNEL_PATTERNS)
ALL_PATTERNS.update(SYSTEM_PATTERNS)


def is_negated_mention(message: str, canonical: str) -> bool:
    """Check if a canonical channel/system term appears negated in the message."""
    pattern = ALL_PATTERNS.get(canonical)
    if not pattern:
        return False
    m = pattern.search(message)
    if not m:
        return False
    mention_start = m.start()
    start = max(0, mention_start - 50)
    prefix = message[start:mention_start]
    return bool(NEGATION_PREFIX.search(prefix))


CLAUSE_SEPARATORS = re.compile(
    r"(?:\s*[.;!?:]\s+|\s*,\s+(?!\s*y|y\s+)\s*|\s+pero\s+|\s+sino\s+|\s+aunque\s+)"
    r"|(?:\s+(?:ahora|actualmente|hoy|en\s+cambio|solo|en\s+realidad)\s+)"
    r"|(?:\s+(?:sin\s+embargo|no\s+obstante)\s+)",
    re.IGNORECASE,
)


def split_semantic_clauses(message: str) -> list[str]:
    """Split a message into semantic clauses for independent evaluation."""
    parts = CLAUSE_SEPARATORS.split(message)
    result = []
    for p in parts:
        p = p.strip()
        if p and len(p) > 2:
            result.append(p)
    if not result:
        result = [message.strip()]
    return result


def classify_clause(clause: str) -> str:
    """Classify a clause as current, negated, past, future, hypothetical, or question."""
    c = clause.strip()
    if c.startswith("¿") or c.startswith("?"):
        return "question"
    if NON_ASSERTIVE_PREFIX.search(c):
        return "hypothetical"
    if TEMPORAL_PAST.search(c):
        return "past"
    if TEMPORAL_FUTURE.search(c):
        return "future"
    if NEGATION_PREFIX.search(c):
        return "negated"
    return "current"


def extract_current_channels(message: str) -> list[str]:
    """Extract channels only from current-assertion clauses in a message."""
    clauses = split_semantic_clauses(message)
    result: list[str] = []
    for clause in clauses:
        cls = classify_clause(clause)
        if cls != "current":
            continue
        found = extract_channels(clause)
        for c in found:
            if c not in result:
                result.append(c)
    return result


def extract_current_systems(message: str) -> list[str]:
    """Extract systems only from current-assertion clauses in a message."""
    clauses = split_semantic_clauses(message)
    result: list[str] = []
    for clause in clauses:
        cls = classify_clause(clause)
        if cls != "current":
            continue
        found = extract_systems(clause)
        for s in found:
            if s not in result:
                result.append(s)
    return result


def is_non_assertive_message(message: str) -> bool:
    """Check if the entire message is a question, hypothetical, or example."""
    msg = message.strip()
    if msg.startswith("¿") or msg.startswith("?"):
        return True
    if NON_ASSERTIVE_PREFIX.search(msg):
        return True
    return False


def is_temporal_non_current(message: str) -> bool:
    """Check if the message refers to past systems/channels or future plans."""
    if TEMPORAL_PAST.search(message):
        return True
    if TEMPORAL_FUTURE.search(message):
        return True
    return False


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
    """Returns 'not_required', 'conditional', 'required', or None.
    None means 'no approval information found' (don't change existing state).
    not_required is checked FIRST to prevent negative statements from
    matching required patterns via substring."""

    for pattern in APPROVAL_NOT_REQUIRED_PATTERNS:
        if pattern.search(message):
            return "not_required"

    for pattern in APPROVAL_CONDITIONAL_PATTERNS:
        if pattern.search(message):
            return "conditional"

    for pattern in APPROVAL_REQUIRED_PATTERNS:
        if pattern.search(message):
            return "required"
    return None


PERIOD_CANONICAL: dict[str, str] = {
    # Spanish → English
    "día": "day", "dia": "day", "días": "day", "dias": "day", "diaria": "day", "diario": "day",
    "semana": "week", "semanas": "week",
    "mes": "month", "meses": "month",
    "año": "year", "ano": "year", "años": "year", "anos": "year",
    # English → English (already canonical)
    "day": "day", "daily": "day",
    "week": "week", "weekly": "week",
    "month": "month", "monthly": "month",
    "year": "year", "yearly": "year",
    # Hebrew → English
    "יום": "day",
    "שבוע": "week",
    "חודש": "month",
    "שנה": "year",
}


def extract_volume(message: str) -> dict | None:
    """Returns {'value': N, 'unit': str|None, 'period': str} or None.
    Period is canonicalized to English (day/week/month/year)."""
    for pattern in VOLUME_PATTERNS:
        m = pattern.search(message)
        if m:
            try:
                val = float(m.group("value"))
            except (ValueError, IndexError):
                continue
            period_raw = (m.group("period") or "day").lower()[:20]
            # Normalize plural for long words (keep 3-char words like "mes" intact)
            if len(period_raw) > 3 and period_raw.endswith("s"):
                period_raw = period_raw[:-1]
            # Canonicalize to English
            period = PERIOD_CANONICAL.get(period_raw, period_raw)
            unit = m.group("unit")
            unit = unit.lower().rstrip("s") if unit else None
            return {
                "value": int(val) if val == int(val) else val,
                "unit": unit,
                "period": period,
            }
    return None


# ── Entity-source relationship ───────────────────────────────────────────

ENTITY_SOURCE_PATTERNS: dict[tuple[str, str], re.Pattern] = {
    # Patterns that associate an entity with a system.
    # Hebrew terms matched WITHOUT \b because Hebrew often uses prefixes (ה, ב, ל).
    # The proximity constraint .{0,50} provides sufficient precision.
    ("inventory", "erp"): re.compile(
        r"(?:\b(?:stock|inventario|inventory)\b|(?:מלאי)).{0,50}(?:\b(?:erp)\b)", re.IGNORECASE),
    ("inventory", "spreadsheet"): re.compile(
        r"(?:\b(?:stock|inventario|inventory)\b|(?:מלאי)).{0,50}"
        r"(?:\b(?:planilla|spreadsheet)\b|(?:גיליון))", re.IGNORECASE),
    ("prices", "spreadsheet"): re.compile(
        r"(?:\b(?:precios?|prices?|pricing)\b|(?:מחירים?)).{0,50}"
        r"(?:\b(?:planilla|spreadsheet|excel)\b|(?:גיליון|אקסל))", re.IGNORECASE),
    ("prices", "crm"): re.compile(
        r"(?:\b(?:precios?|prices?|pricing)\b|(?:מחירים?)).{0,50}(?:\b(?:crm)\b)", re.IGNORECASE),
    ("inventory", "system"): re.compile(
        r"(?:\b(?:stock|inventario|inventory)\b|(?:מלאי)).{0,50}(?:\b(?:sistema|system)\b)", re.IGNORECASE),
    ("prices", "system"): re.compile(
        r"(?:\b(?:precios?|prices?|pricing)\b|(?:מחירים?)).{0,50}(?:\b(?:sistema|system)\b)", re.IGNORECASE),
}


def extract_entity_sources(message: str) -> dict[str, str]:
    """Map entities to their data sources from a message.
    Returns dict like {'inventory': 'erp', 'prices': 'spreadsheet'}."""
    result: dict[str, str] = {}
    for (entity, source), pattern in ENTITY_SOURCE_PATTERNS.items():
        if pattern.search(message):
            # Only set if not already mapped (first match wins)
            if entity not in result:
                result[entity] = source
    return result


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
