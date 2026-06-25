import type { StructuredDiagnosis } from "./publicDiagnosis";

type Locale = "es" | "en" | "he";
type LocalizedText = Record<Locale, string>;

// ---------------------------------------------------------------------------
// Canonical value → localized label maps
// ---------------------------------------------------------------------------

const FEASIBILITY_LABELS: Record<string, LocalizedText> = {
  high: { es: "Alta", en: "High", he: "גבוהה" },
  medium: { es: "Media", en: "Medium", he: "בינונית" },
  low: { es: "Baja", en: "Low", he: "נמוכה" },
  needs_validation: { es: "Requiere validación", en: "Needs validation", he: "דרוש אימות" },
  not_recommended: { es: "No recomendada", en: "Not recommended", he: "לא מומלץ" },
};

const AUTOMATION_MODE_LABELS: Record<string, LocalizedText> = {
  automatic: { es: "Automática", en: "Automatic", he: "אוטומטי" },
  human_in_the_loop: { es: "Con aprobación humana", en: "With human approval", he: "עם אישור אנושי" },
  assisted: { es: "Asistida", en: "Assisted", he: "בסיוע" },
  manual_with_automation_support: { es: "Manual con apoyo automatizado", en: "Manual with automation support", he: "ידני עם תמיכה אוטומטית" },
  not_recommended: { es: "No recomendada", en: "Not recommended", he: "לא מומלץ" },
};

const CONFIDENCE_LABELS: Record<string, LocalizedText> = {
  high: { es: "Alta", en: "High", he: "גבוהה" },
  medium: { es: "Media", en: "Medium", he: "בינונית" },
  low: { es: "Baja", en: "Low", he: "נמוכה" },
};

const AVAILABILITY_LABELS: Record<string, LocalizedText> = {
  available_now: { es: "Disponible para evaluación inmediata", en: "Available for immediate evaluation", he: "זמין להערכה מיידית" },
  requires_validation: { es: "Requiere validación técnica", en: "Requires technical validation", he: "דרוש אימות טכני" },
  custom_solution: { es: "Requiere una solución a medida", en: "Requires a custom solution", he: "דורש פתרון מותאם" },
  not_in_immediate_catalog: { es: "Fuera del catálogo inmediato", en: "Outside immediate catalog", he: "מחוץ לקטלוג המיידי" },
  not_recommended: { es: "No recomendamos automatizarlo de esta forma", en: "Not recommended to automate this way", he: "לא מומלץ להפוך לאוטומטי בדרך זו" },
};

const HUMAN_APPROVAL_LABELS: Record<string, LocalizedText> = {
  required: { es: "Requiere aprobación humana", en: "Requires human approval", he: "נדרש אישור אנושי" },
  conditional: { es: "Aprobación humana condicional", en: "Conditional human approval", he: "אישור אנושי מותנה" },
  not_required: { es: "No requiere aprobación humana", en: "No human approval needed", he: "לא נדרש אישור אנושי" },
  unknown: { es: "No determinado", en: "Not determined", he: "לא נקבע" },
};

const RISK_LABELS: Record<string, LocalizedText> = {
  integration_not_confirmed: { es: "La integración todavía debe validarse", en: "Integration still needs validation", he: "האינטגרציה עדיין דורשת אימות" },
  security_control_required: { es: "El flujo incluye un control de seguridad que debe completar el usuario", en: "Flow includes a security control the user must complete", he: "הזרימה כוללת בקרת אבטחה שהמשתמש חייב להשלים" },
  sensitive_decision: { es: "La decisión requiere control humano", en: "The decision requires human oversight", he: "ההחלטה דורשת פיקוח אנושי" },
  financial_or_reputational_risk: { es: "Riesgo financiero o reputacional", en: "Financial or reputational risk", he: "סיכון פיננסי או תדמיתי" },
  closed_software_dependency: { es: "Dependencia de software cerrado", en: "Closed software dependency", he: "תלות בתוכנה סגורה" },
  stale_price_data: { es: "Los datos pueden estar desactualizados", en: "Data may be outdated", he: "הנתונים עלולים להיות מיושנים" },
};

const ENTITY_LABELS: Record<string, LocalizedText> = {
  inventory: { es: "Stock", en: "Inventory", he: "מלאי" },
  prices: { es: "Precios", en: "Prices", he: "מחירים" },
  customers: { es: "Clientes", en: "Customers", he: "לקוחות" },
  sales_inquiries: { es: "Consultas de venta", en: "Sales inquiries", he: "פניות מכירה" },
  discounts: { es: "Descuentos", en: "Discounts", he: "הנחות" },
  claims: { es: "Reclamos", en: "Claims", he: "תביעות" },
  orders: { es: "Pedidos", en: "Orders", he: "הזמנות" },
  documents: { es: "Documentos", en: "Documents", he: "מסמכים" },
};

const SYSTEM_LABELS: Record<string, LocalizedText> = {
  erp: { es: "ERP", en: "ERP", he: "ERP" },
  crm: { es: "CRM", en: "CRM", he: "CRM" },
  spreadsheet: { es: "Planilla", en: "Spreadsheet", he: "גיליון אלקטרוני" },
  database: { es: "Base de datos", en: "Database", he: "מסד נתונים" },
  inventory_system: { es: "Sistema de stock", en: "Inventory system", he: "מערכת מלאי" },
  closed_windows_application: { es: "Programa de Windows cerrado", en: "Closed Windows application", he: "תוכנת Windows סגורה" },
  proprietary_system: { es: "Software propietario", en: "Proprietary software", he: "תוכנה קניינית" },
};

const CHANNEL_LABELS: Record<string, LocalizedText> = {
  whatsapp: { es: "WhatsApp", en: "WhatsApp", he: "וואטסאפ" },
  gmail: { es: "Gmail", en: "Gmail", he: "ג'ימייל" },
  email: { es: "Email", en: "Email", he: "אימייל" },
  web: { es: "Sitio web", en: "Website", he: "אתר" },
  telegram: { es: "Telegram", en: "Telegram", he: "טלגרם" },
  facebook: { es: "Facebook", en: "Facebook", he: "פייסבוק" },
  instagram: { es: "Instagram", en: "Instagram", he: "אינסטגרם" },
  phone: { es: "Teléfono", en: "Phone", he: "טלפון" },
  chat: { es: "Chat", en: "Chat", he: "צ'אט" },
};

const AUTOMATABLE_STEP_LABELS: Record<string, LocalizedText> = {
  "generate standard replies": {
    es: "generar respuestas estándar",
    en: "generate standard replies",
    he: "יצירת תשובות סטנדרטיות",
  },
};

const HUMAN_STEP_LABELS: Record<string, LocalizedText> = {
  "user completes native MFA control": {
    es: "el usuario completa el control MFA nativo",
    en: "user completes native MFA control",
    he: "המשתמש משלים את בקרת ה-MFA המקורית",
  },
  "approve exceptions or sensitive actions": {
    es: "aprobar excepciones o acciones sensibles",
    en: "approve exceptions or sensitive actions",
    he: "אישור חריגים או פעולות רגישות",
  },
  "user executes core process with automation support": {
    es: "el usuario ejecuta el proceso principal con apoyo de automatización",
    en: "user executes core process with automation support",
    he: "המשתמש מבצע את התהליך המרכזי עם תמיכת אוטומציה",
  },
};

const ASSUMPTION_LABELS: Record<string, LocalizedText> = {
  "data export or API access can be arranged": {
    es: "se puede acordar exportación de datos o acceso por API",
    en: "data export or API access can be arranged",
    he: "ניתן להסדיר יצוא נתונים או גישה דרך API",
  },
  "system data can be accessed or exported": {
    es: "los datos del sistema pueden consultarse o exportarse",
    en: "system data can be accessed or exported",
    he: "ניתן לגשת לנתוני המערכת או לייצא אותם",
  },
  "spreadsheet data is maintained and accessible": {
    es: "los datos de la planilla se mantienen actualizados y accesibles",
    en: "spreadsheet data is maintained and accessible",
    he: "נתוני הגיליון מתוחזקים ונגישים",
  },
  "integration methods are feasible with standard tools": {
    es: "los métodos de integración son factibles con herramientas estándar",
    en: "integration methods are feasible with standard tools",
    he: "שיטות האינטגרציה אפשריות עם כלים סטנדרטיים",
  },
};

const VALIDATION_POINT_LABELS: Record<string, LocalizedText> = {
  "confirm API or export capability": {
    es: "confirmar si existe API o capacidad de exportación",
    en: "confirm API or export capability",
    he: "לאשר אם קיימת API או יכולת יצוא",
  },
  "evaluate RPA or local agent alternative": {
    es: "evaluar alternativa con RPA o agente local",
    en: "evaluate RPA or local agent alternative",
    he: "לבחון חלופה של RPA או סוכן מקומי",
  },
  "confirm spreadsheet update responsibility": {
    es: "confirmar quién mantiene actualizada la planilla",
    en: "confirm spreadsheet update responsibility",
    he: "לאשר מי אחראי לעדכן את הגיליון",
  },
  "define approval rules for exceptions": {
    es: "definir reglas de aprobación para excepciones",
    en: "define approval rules for exceptions",
    he: "להגדיר כללי אישור לחריגים",
  },
  "design automation flow around native MFA control": {
    es: "diseñar el flujo de automatización alrededor del control MFA nativo",
    en: "design automation flow around native MFA control",
    he: "לתכנן את זרימת האוטומציה סביב בקרת ה-MFA המקורית",
  },
  "validate system access and integration method": {
    es: "validar acceso al sistema y método de integración",
    en: "validate system access and integration method",
    he: "לאמת גישה למערכת ושיטת אינטגרציה",
  },
};

const NEXT_STEP_LABELS: Record<string, LocalizedText> = {
  "validate software integration options (API, data export, RPA, local agent)": {
    es: "validar opciones de integración del software: API, exportación de datos, RPA o agente local",
    en: "validate software integration options (API, data export, RPA, local agent)",
    he: "לאמת אפשרויות אינטגרציה לתוכנה: API, יצוא נתונים, RPA או סוכן מקומי",
  },
  "design automation flow around native MFA control with user approval step": {
    es: "diseñar el flujo de automatización alrededor del control MFA nativo con aprobación del usuario",
    en: "design automation flow around native MFA control with user approval step",
    he: "לתכנן את זרימת האוטומציה סביב בקרת ה-MFA המקורית עם שלב אישור משתמש",
  },
  "define approval thresholds and exception handling rules before automation": {
    es: "definir umbrales de aprobación y reglas de manejo de excepciones antes de automatizar",
    en: "define approval thresholds and exception handling rules before automation",
    he: "להגדיר ספי אישור וכללי טיפול בחריגים לפני אוטומציה",
  },
  "evaluate industrial platform compatibility and integration requirements": {
    es: "evaluar compatibilidad de la plataforma industrial y requisitos de integración",
    en: "evaluate industrial platform compatibility and integration requirements",
    he: "לבחון תאימות של הפלטפורמה התעשייתית ודרישות אינטגרציה",
  },
};

// ---------------------------------------------------------------------------
// Lookup helpers
// ---------------------------------------------------------------------------

export function normalizeLocale(locale: string): Locale {
  if (locale === "en" || locale === "he") return locale;
  return "es";
}

function label<T extends string>(
  map: Record<string, LocalizedText>,
  key: T,
  locale: string,
  fallback: string,
): string {
  const entry = map[key];
  if (!entry) return fallback;
  const normalizedLocale = normalizeLocale(locale);
  return entry[normalizedLocale] || entry.es || fallback;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function formatFeasibility(value: string, locale: string): string {
  return label(FEASIBILITY_LABELS, value, locale, value);
}

export function formatAutomationMode(value: string, locale: string): string {
  return label(AUTOMATION_MODE_LABELS, value, locale, value);
}

export function formatConfidence(value: string, locale: string): string {
  return label(CONFIDENCE_LABELS, value, locale, value);
}

export function formatAvailability(value: string, locale: string): string {
  return label(AVAILABILITY_LABELS, value, locale, value);
}

export function formatHumanApproval(value: string, locale: string): string {
  return label(HUMAN_APPROVAL_LABELS, value, locale, value.replace(/_/g, " "));
}

export function formatRisk(value: string, locale: string): string {
  return label(RISK_LABELS, value, locale, value.replace(/_/g, " "));
}

export function formatEntity(value: string, locale: string): string {
  return label(ENTITY_LABELS, value, locale, value);
}

export function formatSystem(value: string, locale: string): string {
  return label(SYSTEM_LABELS, value, locale, value);
}

export function formatChannel(value: string, locale: string): string {
  return label(CHANNEL_LABELS, value, locale, value);
}

export function formatAutomatableStep(value: string, locale: string): string {
  const receiveMatch = value.match(/^receive inquiries from (.+)$/);
  if (receiveMatch) {
    const channels = receiveMatch[1]
      .split(/\s+and\s+/)
      .map(channel => formatChannel(channel, locale))
      .join(locale === "he" ? " ו" : locale === "en" ? " and " : " y ");
    return label(
      {
        receive: {
          es: `recibir consultas desde ${channels}`,
          en: `receive inquiries from ${channels}`,
          he: `קבלת פניות מ${channels}`,
        },
      },
      "receive",
      locale,
      value,
    );
  }

  const retrieveMatch = value.match(/^retrieve (.+) from (.+)$/);
  if (retrieveMatch) {
    const entity = formatEntity(retrieveMatch[1], locale);
    const source = formatSystem(retrieveMatch[2], locale);
    return label(
      {
        retrieve: {
          es: `consultar ${entity} desde ${source}`,
          en: `retrieve ${entity} from ${source}`,
          he: `שליפת ${entity} מתוך ${source}`,
        },
      },
      "retrieve",
      locale,
      value,
    );
  }

  return label(AUTOMATABLE_STEP_LABELS, value, locale, value);
}

export function formatHumanStep(value: string, locale: string): string {
  return label(HUMAN_STEP_LABELS, value, locale, value);
}

export function formatAssumption(value: string, locale: string): string {
  return label(ASSUMPTION_LABELS, value, locale, value);
}

export function formatValidationPoint(value: string, locale: string): string {
  const integrationMatch = value.match(/^confirm (.+) integration method for (.+)$/);
  if (integrationMatch) {
    const source = formatSystem(integrationMatch[1], locale);
    const entity = formatEntity(integrationMatch[2], locale);
    return label(
      {
        integration: {
          es: `confirmar método de integración de ${source} para ${entity}`,
          en: `confirm ${source} integration method for ${entity}`,
          he: `לאשר שיטת אינטגרציה של ${source} עבור ${entity}`,
        },
      },
      "integration",
      locale,
      value,
    );
  }
  return label(VALIDATION_POINT_LABELS, value, locale, value);
}

export function formatNextStep(value: string, locale: string): string {
  const validateMatch = value.match(/^validate (.+) access, then design the (.+) response flow( with approval rules)?$/);
  if (validateMatch) {
    const systems = validateMatch[1]
      .split(/\s+and\s+/)
      .map(system => formatSystem(system, locale))
      .join(locale === "he" ? " ו" : locale === "en" ? " and " : " y ");
    const channels = validateMatch[2]
      .split(/\s+and\s+/)
      .map(channel => formatChannel(channel, locale))
      .join(locale === "he" ? " ו" : locale === "en" ? " and " : " y ");
    const approval = Boolean(validateMatch[3]);
    if (locale === "en") {
      return `validate ${systems} access, then design the ${channels} response flow${approval ? " with approval rules" : ""}`;
    }
    if (locale === "he") {
      return `לאמת גישה ל${systems}, ואז לתכנן את זרימת המענה עבור ${channels}${approval ? " עם כללי אישור" : ""}`;
    }
    return `validar acceso a ${systems} y luego diseñar el flujo de respuesta para ${channels}${approval ? " con reglas de aprobación" : ""}`;
  }

  return label(NEXT_STEP_LABELS, value, locale, value);
}

// ---------------------------------------------------------------------------
// Section titles (localized)
// ---------------------------------------------------------------------------

export const SECTION_TITLES: Record<string, LocalizedText> = {
  diagnosis_heading: { es: "Tu orientación inicial", en: "Your initial assessment", he: "ההכוונה הראשונית שלך" },
  feasibility: { es: "Factibilidad inicial", en: "Initial feasibility", he: "היתכנות ראשונית" },
  automation_mode: { es: "Modalidad", en: "Mode", he: "אופן פעולה" },
  confidence: { es: "Confianza", en: "Confidence", he: "רמת ביטחון" },
  what_can_automate: { es: "Qué puede automatizarse", en: "What can be automated", he: "מה ניתן להפוך לאוטומטי" },
  human_intervention: { es: "Qué requiere intervención humana", en: "What requires human intervention", he: "מה דורש התערבות אנושית" },
  channels_systems: { es: "Canales y sistemas", en: "Channels and systems", he: "ערוצים ומערכות" },
  risks: { es: "Riesgos identificados", en: "Identified risks", he: "סיכונים שזוהו" },
  assumptions: { es: "Supuestos considerados", en: "Assumptions considered", he: "הנחות שנשקלו" },
  validation_points: { es: "Puntos a validar", en: "Points to validate", he: "נקודות לאימות" },
  next_step: { es: "Próximo paso", en: "Next step", he: "הצעד הבא" },
  availability: { es: "Disponibilidad", en: "Availability", he: "זמינות" },
  fallback_note: { es: "Nota: la respuesta automática no pudo generarse por un problema temporal. La orientación estructurada está disponible.", en: "Note: the automatic response could not be generated due to a temporary issue. The structured assessment is still available.", he: "הערה: לא ניתן היה ליצור את התשובה האוטומטית עקב בעיה זמנית. ההכוונה המבנית עדיין זמינה." },
  error_503: { es: "{name} no está disponible en este momento. La conversación no se perdió; podés volver a intentarlo.", en: "{name} is not available right now. The conversation was not lost; you can try again.", he: "{name} לא זמין כרגע. השיחה לא אבדה; תוכל לנסות שוב." },
};

export function sectionTitle(key: string, locale: string, params?: Record<string, string>): string {
  const entry = SECTION_TITLES[key];
  if (!entry) return key;
  const normalizedLocale = normalizeLocale(locale);
  let text = entry[normalizedLocale] || entry.es || key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.replace(`{${k}}`, v);
    }
  }
  return text;
}

// ---------------------------------------------------------------------------
// Direction / lang helpers
// ---------------------------------------------------------------------------

export function directionForLocale(locale: string): "ltr" | "rtl" {
  return locale === "he" ? "rtl" : "ltr";
}

export function langAttr(locale: string): string {
  return locale === "he" ? "he" : locale === "en" ? "en" : "es";
}

// ---------------------------------------------------------------------------
// Entity-source display
// ---------------------------------------------------------------------------

export function formatEntitySources(sources: Record<string, string>, locale: string): Array<{ entity: string; source: string }> {
  return Object.entries(sources).map(([entity, source]) => ({
    entity: formatEntity(entity, locale),
    source: formatSystem(source, locale),
  }));
}

// ---------------------------------------------------------------------------
// Guard: check if diagnosis is a valid object
// ---------------------------------------------------------------------------

export function isValidDiagnosis(d: unknown): d is StructuredDiagnosis {
  if (!d || typeof d !== "object") return false;
  const obj = d as Record<string, unknown>;
  return (
    typeof obj.version === "string" &&
    typeof obj.feasibility === "string" &&
    typeof obj.automation_mode === "string" &&
    Array.isArray(obj.channels) &&
    Array.isArray(obj.systems)
  );
}
