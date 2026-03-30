/**
 * Inicialización de i18next con:
 * - i18next-http-backend: carga traducciones desde /public/locales/{lang}/translation.json
 * - i18next-browser-languagedetector: detecta idioma del navegador
 * - Soporte para ES, RU, EN con fallback a "en"
 */
import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import HttpBackend from "i18next-http-backend";
import { initReactI18next } from "react-i18next";

i18n
  .use(HttpBackend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    supportedLngs: ["es", "ru", "en"],
    fallbackLng: "ru",
    lng: "ru",
    defaultNS: "translation",
    backend: {
      loadPath: "/locales/{{lng}}/{{ns}}.json",
    },
    detection: {
      order: ["localStorage", "navigator", "htmlTag"],
      lookupLocalStorage: "i18nextLng",
      caches: ["localStorage"],
    },
    interpolation: {
      escapeValue: false, // React ya escapa por defecto
    },
    react: {
      useSuspense: true,
    },
  });

export default i18n;
