import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getArticles } from "@/services/api";
import ArticleCard from "@/components/ArticleCard/ArticleCard";
import "./Dashboard.css";

export default function Dashboard() {
  const { t } = useTranslation();

  const { data, isLoading } = useQuery({
    queryKey: ["articles", "recent"],
    queryFn: () => getArticles({ ordering: "-created_at" }),
  });

  const { data: aiData } = useQuery({
    queryKey: ["articles", "ai-processed"],
    queryFn: () => getArticles({ ai_processed: true, ordering: "-created_at" }),
  });

  return (
    <div className="dashboard">
      <h1 className="dashboard__title">{t("dashboard.title")}</h1>
      <p className="dashboard__description">{t("dashboard.description")}</p>

      {/* Estadísticas */}
      <div className="dashboard__stats">
        <div className="stat-card">
          <span className="stat-card__value">{data?.count ?? "—"}</span>
          <span className="stat-card__label">{t("dashboard.stat_total")}</span>
        </div>
        <div className="stat-card">
          <span className="stat-card__value">{aiData?.count ?? "—"}</span>
          <span className="stat-card__label">{t("dashboard.stat_ai_processed")}</span>
        </div>
      </div>

      {/* CTA Búsqueda */}
      <div className="dashboard__cta">
        <Link to="/search" className="dashboard__cta-btn">
          {t("dashboard.start_search")}
        </Link>
      </div>

      {/* Artículos recientes */}
      <section className="dashboard__section">
        <h2 className="dashboard__section-title">{t("dashboard.recent")}</h2>
        {isLoading ? (
          <p className="dashboard__loading">{t("common.loading")}</p>
        ) : (
          <div className="dashboard__grid">
            {data?.results.slice(0, 6).map((article) => (
              <ArticleCard key={article.id} article={article} />
            ))}
          </div>
        )}
        {data && data.count > 6 && (
          <Link to="/search" className="dashboard__see-all">
            {t("dashboard.see_all", { count: data.count })}
          </Link>
        )}
      </section>
    </div>
  );
}
