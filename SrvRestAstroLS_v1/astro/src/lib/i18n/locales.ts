import {
  DEFAULT_DIRECTION as GLOBAL_DEFAULT_DIRECTION,
  DEFAULT_LOCALE as GLOBAL_DEFAULT_LOCALE,
  LOCALE_DIRECTION,
  SUPPORTED_LOCALES as GLOBAL_SUPPORTED_LOCALES,
} from "../../components/global.js";

export const SUPPORTED_LOCALES = GLOBAL_SUPPORTED_LOCALES;
export const DEFAULT_LOCALE = GLOBAL_DEFAULT_LOCALE;
export const DEFAULT_DIRECTION = GLOBAL_DEFAULT_DIRECTION;

export type Locale = (typeof SUPPORTED_LOCALES)[number];
export type TextDirection = (typeof LOCALE_DIRECTION)[Locale];

export function isSupportedLocale(locale: string): locale is Locale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(locale);
}

export function normalizeLocale(locale?: string): Locale {
  return locale && isSupportedLocale(locale) ? locale : DEFAULT_LOCALE;
}

export function getDirection(locale?: string): TextDirection {
  return LOCALE_DIRECTION[normalizeLocale(locale)];
}
