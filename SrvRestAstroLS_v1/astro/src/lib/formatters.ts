import { DEFAULT_LOCALE, normalizeLocale } from "./i18n";

function dateLocale(locale?: string) {
  return normalizeLocale(locale ?? DEFAULT_LOCALE);
}

export function formatDate(value: string | null, locale?: string): string {
  if (!value) return "Fecha pendiente";

  const normalizedValue = value.includes("T") ? value : `${value}T12:00:00Z`;
  return new Intl.DateTimeFormat(dateLocale(locale), { dateStyle: "medium" }).format(new Date(normalizedValue));
}

export function formatDateTime(value: string | null, locale?: string): string {
  if (!value) return "Primera ejecución pendiente";

  return new Intl.DateTimeFormat(dateLocale(locale), {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatDuration(seconds: number | null, locale?: string): string {
  if (seconds === null) return "En curso";

  return `${new Intl.NumberFormat(dateLocale(locale)).format(seconds)} s`;
}
