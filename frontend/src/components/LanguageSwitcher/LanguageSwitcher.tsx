import React from "react";
import { useTranslation } from "react-i18next";
import "./LanguageSwitcher.css";

const LANGUAGES = [
  { code: "es", label: "ES" },
  { code: "ru", label: "RU" },
  { code: "en", label: "EN" },
] as const;

export default function LanguageSwitcher() {
  const { i18n } = useTranslation();
  const current = i18n.language.slice(0, 2);

  return (
    <div className="lang-switcher" role="group" aria-label="Seleccionar idioma">
      {LANGUAGES.map(({ code, label }) => (
        <button
          key={code}
          className={`lang-switcher__btn${current === code ? " lang-switcher__btn--active" : ""}`}
          onClick={() => i18n.changeLanguage(code)}
          aria-pressed={current === code}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
