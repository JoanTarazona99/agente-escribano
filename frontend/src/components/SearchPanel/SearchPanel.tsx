import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import type { SourceDatabase } from "@/types";
import "./SearchPanel.css";

const DEFAULT_QUERY =
  "water dissociation recombination electromembrane bipolar membrane transport";

const ALL_SOURCES: SourceDatabase[] = ["arxiv", "elibrary", "scopus", "wos"];
const DISABLED_SOURCES: Set<SourceDatabase> = new Set(["wos"]);

interface SearchPanelProps {
  onSearch: (query: string, sources: SourceDatabase[], maxPerSource: number) => void;
  isLoading?: boolean;
}

export default function SearchPanel({ onSearch, isLoading = false }: SearchPanelProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [sources, setSources] = useState<SourceDatabase[]>(["arxiv", "elibrary"]);
  const [maxPerSource, setMaxPerSource] = useState(10);

  const toggleSource = (src: SourceDatabase) => {
    setSources((prev) =>
      prev.includes(src) ? prev.filter((s) => s !== src) : [...prev, src],
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (sources.length === 0) return;
    onSearch(query.trim() || DEFAULT_QUERY, sources, maxPerSource);
  };

  const handleTextareaKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isLoading && sources.length > 0) {
        onSearch(query.trim() || DEFAULT_QUERY, sources, maxPerSource);
      }
    }
  };

  return (
    <form className="search-panel" onSubmit={handleSubmit} aria-label={t("search.form_label")}>
      <h2 className="search-panel__title">{t("search.title")}</h2>
      <p className="search-panel__subtitle">{t("search.subtitle")}</p>

      <div className="search-panel__field">
        <label htmlFor="search-query" className="search-panel__label">
          {t("search.query_label")}
        </label>
        <textarea
          id="search-query"
          className="search-panel__textarea"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleTextareaKeyDown}
          rows={3}
          placeholder={DEFAULT_QUERY}
        />
      </div>

      <div className="search-panel__field">
        <span className="search-panel__label">{t("search.sources_label")}</span>
        <div className="search-panel__sources">
          {ALL_SOURCES.map((src) => {
            const isDisabled = DISABLED_SOURCES.has(src);
            return (
              <label
                key={src}
                className={`search-panel__source-item${isDisabled ? " search-panel__source-item--disabled" : ""}`}
                title={isDisabled ? t("search.source_unavailable") : undefined}
              >
                <input
                  type="checkbox"
                  checked={!isDisabled && sources.includes(src)}
                  onChange={() => toggleSource(src)}
                  disabled={isDisabled}
                />
                <span className={`badge badge--${src}`}>{src.toUpperCase()}</span>
                {isDisabled && <span className="search-panel__soon">{t("search.coming_soon")}</span>}
              </label>
            );
          })}
        </div>
      </div>

      <div className="search-panel__bottom">
        <div className="search-panel__field search-panel__field--inline">
          <label htmlFor="max-per-source" className="search-panel__label">
            {t("search.max_per_source_label")}
          </label>
          <input
            id="max-per-source"
            type="number"
            className="search-panel__number"
            value={maxPerSource}
            min={1}
            max={200}
            onChange={(e) => setMaxPerSource(Number(e.target.value))}
          />
        </div>
        <button
          type="submit"
          className="search-panel__submit"
          disabled={isLoading || sources.length === 0}
          title={isLoading ? t("search.searching") : t("search.submit")}
        >
          {isLoading ? (
            <span className="search-panel__submit-spinner">⏳</span>
          ) : (
            <span>→</span>
          )}
        </button>
      </div>
    </form>
  );
}
