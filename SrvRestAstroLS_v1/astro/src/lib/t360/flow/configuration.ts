// Team360 Flow — configuración de routing.
// El shape sigue los campos reales de flow_sectors/flow_sector_levels.
// closureSupervisorDestination es una proyección UX de la autoridad derivada
// por closureApprovalLevel; no representa un endpoint mutativo.

export interface FlowConfigurationLevel {
  id: string;
  level: number;
  label: string;
  channel: string;
  destination: string;
  active: boolean;
  role: string;
  firstResponseSlaSeconds: number | null;
}

export interface FlowSectorConfiguration {
  sectorId: string;
  displayName: string;
  active: boolean;
  levels: FlowConfigurationLevel[];
  closureApprovalLevel: number | null;
  closureSupervisorDestination: string;
}

export type FlowConfigurationSaveHandler = (configuration: FlowSectorConfiguration[]) => Promise<void> | void;

export const FLOW_CONFIGURATION_DEMO: FlowSectorConfiguration[] = [
  {
    sectorId: "alumbrado",
    displayName: "Alumbrado Público",
    active: true,
    closureApprovalLevel: 2,
    closureSupervisorDestination: "alumbrado.n2@alquimiablue.com",
    levels: [
      {
        id: "alumbrado-level-1",
        level: 1,
        label: "Nivel 1",
        channel: "email",
        destination: "alumbrado.n1@alquimiablue.com",
        active: true,
        role: "Primera respuesta",
        firstResponseSlaSeconds: 30,
      },
      {
        id: "alumbrado-level-2",
        level: 2,
        label: "Nivel 2",
        channel: "email",
        destination: "alumbrado.n2@alquimiablue.com",
        active: true,
        role: "Escalamiento",
        firstResponseSlaSeconds: 30,
      },
      {
        id: "alumbrado-level-3",
        level: 3,
        label: "Nivel 3",
        channel: "email",
        destination: "alumbrado.n3@alquimiablue.com",
        active: true,
        role: "Escalamiento avanzado",
        firstResponseSlaSeconds: null,
      },
    ],
  },
];

export function cloneFlowConfiguration(configuration: FlowSectorConfiguration[]): FlowSectorConfiguration[] {
  return configuration.map((sector) => ({
    ...sector,
    levels: sector.levels.map((level) => ({ ...level })),
  }));
}

export function configurationFingerprint(configuration: FlowSectorConfiguration[]): string {
  return JSON.stringify(configuration);
}

export function validateFlowEmail(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return "El destinatario es obligatorio";
  if (/\s/.test(trimmed)) return "Revisá los espacios del email";
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(trimmed)) return "Ingresá un email válido";
  return null;
}

export function flowLevelRole(level: number): string {
  if (level === 1) return "Primera respuesta";
  if (level === 2) return "Escalamiento";
  return "Escalamiento avanzado";
}

export function flowChannelLabel(channel: string): string {
  return channel === "email" ? "Correo electrónico" : channel;
}
