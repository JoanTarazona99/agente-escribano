import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getHealth } from "@/services/api";
import type { HealthResponse } from "@/services/api";
import LanguageSwitcher from "@/components/LanguageSwitcher/LanguageSwitcher";
import "./Settings.css";

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`settings__dot ${ok ? "settings__dot--ok" : "settings__dot--err"}`}
      aria-label={ok ? "OK" : "Error"}
    />
  );
}

export default function Settings() {
  const { t } = useTranslation();
  const { data: health, isLoading, isError } = useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 30_000,
    retry: 1,
  });

  return (
    <div className="settings">
      <h1 className="settings__title">{t("settings.title")}</h1>

      {/* Idioma */}
      <section className="settings__section">
        <h2>{t("settings.language")}</h2>
        <p className="settings__description">{t("settings.language_description")}</p>
        <LanguageSwitcher />
      </section>

      {/* Estado del sistema */}
      <section className="settings__section">
        <h2>{t("settings.system_status")}</h2>
        {isLoading && <p className="settings__description">{t("common.loading")}</p>}
        {isError && <p className="settings__description settings__err">{t("settings.health_error")}</p>}
        {health && (
          <div className="settings__health">
            <div className="settings__health-row">
              <StatusDot ok={health.database.ok} />
              <span><strong>{t("settings.database")}:</strong> {health.database.ok ? "OK" : health.database.error}</span>
            </div>
            <div className="settings__health-row">
              <StatusDot ok={health.ollama.ok} />
              <span>
                <strong>Ollama:</strong>{" "}
                {health.ollama.ok
                  ? `${health.ollama.model} (${health.ollama.available_models?.length ?? 0} ${t("settings.models_available")})`
                  : health.ollama.error ?? "Offline"}
              </span>
            </div>
            <div className="settings__health-row">
              <span>📊 <strong>{t("settings.stats")}:</strong> {health.stats.total_articles} {t("settings.articles")} · {health.stats.ai_processed} {t("settings.ai_analyzed")}</span>
            </div>
          </div>
        )}
      </section>

      {/* API Keys */}
      <section className="settings__section">
        <h2>{t("settings.api_keys")}</h2>
        <p className="settings__description">{t("settings.api_keys_description")}</p>
        <div className="settings__info">
          <p><strong>Scopus:</strong> {t("settings.key_pending")}</p>
          <p><strong>Web of Science:</strong> {t("settings.key_pending")}</p>
          <p><strong>arXiv:</strong> {t("settings.key_not_required")}</p>
          <p><strong>eLIBRARY:</strong> {t("settings.key_not_required")}</p>
        </div>
      </section>
    </div>
  );
}
