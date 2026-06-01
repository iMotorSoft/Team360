import { messagesEn } from "./messages.en";
import { messagesEs } from "./messages.es";
import { messagesHe } from "./messages.he";
import {
  DEFAULT_DIRECTION,
  DEFAULT_LOCALE,
  getDirection,
  normalizeLocale,
  SUPPORTED_LOCALES,
  type Locale,
  type TextDirection,
} from "./locales";

type Messages = Record<string, string>;

const messagesByLocale: Record<Locale, Messages> = {
  es: messagesEs,
  en: messagesEn,
  he: messagesHe,
};

export function t(key: string, locale: Locale = DEFAULT_LOCALE): string {
  return messagesByLocale[locale][key] ?? messagesEs[key as keyof typeof messagesEs] ?? key;
}

export {
  DEFAULT_DIRECTION,
  DEFAULT_LOCALE,
  getDirection,
  normalizeLocale,
  SUPPORTED_LOCALES,
  type Locale,
  type TextDirection,
};
