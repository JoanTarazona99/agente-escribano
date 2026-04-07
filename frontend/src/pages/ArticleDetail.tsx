import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getArticle } from "@/services/api";
import MathText from "@/components/MathText/MathText";
import type { Article } from "@/types";
import "./ArticleDetail.css";

function getPdfUrl(article: Article): string | null {
  if (article.source_db === "arxiv" && article.url) {
    return article.url.replace("/abs/", "/pdf/");
  }
  return null;
}

interface ArticleDetailProps {
  articleId: number;
  onClose?: () => void;
}

export default function ArticleDetail({ articleId, onClose }: ArticleDetailProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language.slice(0, 2);
  const idStr = String(articleId);

  const { data: article, isLoading } = useQuery({
    queryKey: ["article", idStr],
    queryFn: () => getArticle(articleId),
    enabled: articleId > 0,
  });

  if (isLoading) return <p className="detail__loading">{t("common.loading")}</p>;
  if (!article) return <p>{t("common.not_found")}</p>;

  const title =
    lang === "ru" && (article.title_ru || article.title)
      ? article.title_ru || article.title
      : lang === "es" && article.title_es
        ? article.title_es
        : lang === "en" && article.title_en
          ? article.title_en
          : article.title;

  const abstract =
    lang === "ru" && (article.abstract_ru || article.abstract_original)
      ? article.abstract_ru || article.abstract_original
      : lang === "es" && article.abstract_es
        ? article.abstract_es
        : lang === "en" && article.abstract_en
          ? article.abstract_en
          : article.abstract_original;

  return (
    <div className="detail">
      {onClose && (
        <button className="detail__close" onClick={onClose}>
          ✕
        </button>
      )}

      <div className="detail__header">
        <span className={`badge badge--${article.source_db || ""}`}>
          {article.source_db?.toUpperCase() || ""}
        </span>
        {article.article_type && article.article_type !== "unknown" && (
          <span className="detail__type">{t(`article_type.${article.article_type}`)}</span>
        )}
      </div>

      <h1 className="detail__title"><MathText text={title} /></h1>

      {article.authors && <p className="detail__authors">{article.authors}</p>}

      <div className="detail__meta">
        {article.year && <span>{article.year}</span>}
        {article.journal && <span>{article.journal}</span>}
        {article.has_doi && (
          <a href={article.doi_url} target="_blank" rel="noopener noreferrer">
            DOI: {article.doi}
          </a>
        )}
        {article.url && (
          <a href={article.url} target="_blank" rel="noopener noreferrer">
            {t("article.open_source")}
          </a>
        )}
      </div>

      {getPdfUrl(article) && (
        <a
          href={getPdfUrl(article)!}
          target="_blank"
          rel="noopener noreferrer"
          className="detail__pdf-btn"
        >
          📄 {t("article.download_pdf")}
        </a>
      )}

      {abstract && (
        <section className="detail__section">
          <h2>{t("article.abstract")}</h2>
          <p className="detail__abstract">
            <MathText text={abstract} />
          </p>
        </section>
      )}

      {article.keywords && (
        <section className="detail__section">
          <h2>{t("article.keywords")}</h2>
          <div className="detail__keywords">
            {article.keywords.split(",").map((kw, i) => (
              <span key={i} className="detail__keyword">{kw.trim()}</span>
            ))}
          </div>
        </section>
      )}

      {/* AI Results (read-only — analyze button is in Studio panel) */}
      {article.ai_processed && (
        <section className="detail__section detail__ai-section">
          <h2>{t("article.ai_analysis_title")}</h2>

          {(() => {
            const summary =
              lang === "ru" ? (article.ai_summary_ru || article.ai_summary)
              : lang === "es" ? (article.ai_summary_es || article.ai_summary)
              : (article.ai_summary_en || article.ai_summary);
            return summary ? (
              <div className="detail__ai-block">
                <h3>{t("article.ai_summary")}</h3>
                <p>{summary}</p>
              </div>
            ) : null;
          })()}

          {(() => {
            const analysis =
              lang === "ru" ? (article.ai_analysis_ru || article.ai_analysis)
              : lang === "es" ? (article.ai_analysis_es || article.ai_analysis)
              : (article.ai_analysis_en || article.ai_analysis);
            return analysis ? (
              <div className="detail__ai-block">
                <h3>{t("article.ai_full_analysis")}</h3>
                <pre className="detail__ai-analysis">{analysis}</pre>
              </div>
            ) : null;
          })()}
        </section>
      )}
    </div>
  );
}
