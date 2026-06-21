import type {
  T360AssistantTurnResponse,
  T360DiagnosisSnapshot,
  T360InteractionBlock,
} from "./types";

export const t360InteractionFixtureSessionId = "lab_t360_interaction_001";

export const t360InteractionBlockFixtures: T360InteractionBlock[] = [
  {
    type: "next_step_choice",
    title: "Próximo paso recomendado",
    description: "Elegí cómo querés avanzar con esta orientación inicial.",
    actions: [
      {
        id: "show-preliminary",
        label: "Ver diagnóstico",
        style: "primary",
        intent: "show_preliminary_diagnosis",
      },
      {
        id: "continue-discovery",
        label: "Seguir conversando",
        style: "secondary",
        intent: "continue_conversation",
      },
      {
        id: "human-review",
        label: "Revisión humana",
        style: "outline",
        intent: "request_human_review",
      },
    ],
  },
  {
    type: "single_choice",
    question: "¿Cuál canal concentra hoy la mayor parte de las consultas?",
    helper_text: "Usá una opción para orientar el diagnóstico sin abrir un formulario largo.",
    required: true,
    options: [
      {
        id: "whatsapp",
        label: "WhatsApp",
        value: "whatsapp",
        description: "Consultas comerciales o soporte operativo en conversaciones cortas.",
        badge: "Canal principal",
        availability_status: "available_today",
      },
      {
        id: "email",
        label: "Email",
        value: "email",
        description: "Bandejas compartidas con respuestas repetitivas.",
        availability_status: "feasible",
      },
      {
        id: "marketplace",
        label: "Marketplace",
        value: "marketplace",
        description: "Requiere revisar credenciales, límites y reglas del canal.",
        availability_status: "requires_integration",
      },
    ],
    submit_action: {
      id: "submit-channel",
      label: "Continuar",
      style: "primary",
      intent: "answer_choice",
    },
  },
  {
    type: "multi_choice",
    question: "¿Qué sistemas deberían consultarse para responder bien?",
    helper_text: "Seleccioná hasta tres fuentes relevantes.",
    min_selected: 1,
    max_selected: 3,
    options: [
      {
        id: "erp",
        label: "ERP",
        value: "erp",
        description: "Stock, pedidos, clientes o condiciones comerciales.",
        availability_status: "requires_integration",
      },
      {
        id: "spreadsheet",
        label: "Planillas",
        value: "spreadsheet",
        description: "Precios, reglas o catálogos mantenidos por el equipo.",
        availability_status: "feasible",
      },
      {
        id: "crm",
        label: "CRM",
        value: "crm",
        description: "Historial comercial y estado de oportunidades.",
        availability_status: "planned_extension",
      },
      {
        id: "free-text",
        label: "Texto libre",
        value: "free_text",
        description: "No recomendable como única fuente de verdad operativa.",
        availability_status: "not_recommended",
      },
    ],
    submit_action: {
      id: "submit-systems",
      label: "Guardar selección",
      style: "primary",
      intent: "submit_choices",
    },
  },
  {
    type: "missing_requirements",
    title: "Datos que faltan para cerrar el alcance",
    description: "Estos puntos definen si el diagnóstico puede pasar de preliminar a implementable.",
    requirements: [
      {
        id: "inventory-source",
        label: "Fuente confiable de stock",
        description: "Confirmar si el ERP expone inventario por API o export programado.",
        status: "partial",
        required_for: "implementation",
      },
      {
        id: "approval-policy",
        label: "Reglas de aprobación",
        description: "Definir quién aprueba descuentos, excepciones o mensajes sensibles.",
        status: "missing",
        required_for: "full_diagnosis",
      },
      {
        id: "channel-volume",
        label: "Volumen por canal",
        description: "Ya se informó un rango operativo diario.",
        status: "confirmed",
        required_for: "preliminary_diagnosis",
      },
    ],
    actions: [
      {
        id: "continue-missing",
        label: "Completar datos",
        style: "primary",
        intent: "continue_conversation",
      },
      {
        id: "request-review",
        label: "Pedir revisión",
        style: "outline",
        intent: "request_human_review",
      },
    ],
  },
  {
    type: "product_fit_card",
    product_code: "pkg_sales_diagnosis",
    product_name: "Diagnóstico de automatización comercial",
    fit_score: 82,
    status: "available_today",
    summary: "Buen encaje para ordenar el flujo de consultas y separar respuestas automáticas de aprobaciones humanas.",
    good_fit_reasons: [
      "Canales y volumen están claros.",
      "Hay reglas repetibles para respuestas estándar.",
      "El equipo puede validar excepciones antes de automatizar acciones sensibles.",
    ],
    limitations: [
      "La integración con ERP debe validarse antes de prometer stock en tiempo real.",
      "Las reglas de descuento necesitan responsable de aprobación.",
    ],
    recommended_next_step: "Confirmar acceso a ERP y planillas para diseñar el primer flujo asistido.",
    actions: [
      {
        id: "request-contact",
        label: "Coordinar revisión",
        style: "primary",
        intent: "request_contact",
      },
      {
        id: "current-diagnosis",
        label: "Ver diagnóstico",
        style: "secondary",
        intent: "show_current_diagnosis",
      },
    ],
  },
  {
    type: "diagnosis_action_card",
    title: "Orientación lista para revisar",
    summary: "El caso es factible si se valida la integración de inventario y se mantiene aprobación humana para excepciones.",
    status: "feasible",
    confidence: "high",
    primary_action: {
      id: "show-current",
      label: "Abrir diagnóstico",
      style: "primary",
      intent: "show_current_diagnosis",
    },
    secondary_actions: [
      {
        id: "continue-context",
        label: "Agregar contexto",
        style: "outline",
        intent: "continue_conversation",
      },
      {
        id: "close-flow",
        label: "Cerrar",
        style: "ghost",
        intent: "close",
      },
    ],
  },
];

export const t360DiagnosisFixture: T360DiagnosisSnapshot = {
  status: "preliminary",
  title: "Diagnóstico preliminar de automatización comercial",
  summary: "Team360 puede asistir respuestas comerciales repetitivas con aprobación humana para condiciones sensibles.",
  automation_fit: {
    score: 78,
    label: "good",
  },
  availability_status: "feasible",
  recommended_path: [
    "Confirmar fuentes de stock y precios.",
    "Definir reglas de aprobación humana.",
    "Probar un flujo piloto sobre consultas frecuentes.",
  ],
  detected_use_case: {
    label: "Respuesta asistida a consultas comerciales",
    category: "sales_operations",
  },
  suggested_products: [
    {
      product_code: "pkg_sales_diagnosis",
      product_name: "Diagnóstico de automatización comercial",
      status: "available_today",
      fit_score: 82,
    },
    {
      product_code: "pkg_channel_assistant",
      product_name: "Asistente multicanal operativo",
      status: "planned_extension",
      fit_score: 64,
    },
  ],
  risks: [
    "El stock en tiempo real depende de la integración con ERP.",
    "Las excepciones comerciales necesitan reglas de aprobación explícitas.",
  ],
  missing_requirements: [
    {
      id: "erp-access",
      label: "Acceso técnico al ERP",
      status: "partial",
      required_for: "implementation",
    },
    {
      id: "approval-owner",
      label: "Responsable de aprobación",
      status: "missing",
      required_for: "handoff",
    },
  ],
  next_best_action: {
    id: "request-human-review",
    label: "Pedir revisión humana",
    style: "primary",
    intent: "request_human_review",
  },
};

export const t360AssistantTurnFixture: T360AssistantTurnResponse = {
  assistant_text: "Puedo darte una orientación inicial y marcar qué falta validar.",
  conversation_state: {
    session_id: t360InteractionFixtureSessionId,
    turn_count: 4,
    phase: "preliminary_diagnosis",
    known_slots: {
      channels: ["whatsapp", "email"],
      volume: "80_daily",
    },
    missing_slots: ["erp_access", "approval_owner"],
    can_show_preliminary_diagnosis: true,
    should_offer_diagnosis_now: true,
    last_user_intent: "request_diagnosis",
  },
  interaction_block: t360InteractionBlockFixtures[0],
  diagnosis: t360DiagnosisFixture,
};
