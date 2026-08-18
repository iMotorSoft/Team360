// Formateo de timestamps para la vista Flow.
// A diferencia de lib/formatters.ts, los campos opcionales del contrato
// ejecutivo no producen textos de relleno: valor ausente -> "—".

const EMPTY = "—";

export function flowDateTime(value: string | null | undefined): string {
  if (!value) return EMPTY;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return EMPTY;
  return new Intl.DateTimeFormat("es-AR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
