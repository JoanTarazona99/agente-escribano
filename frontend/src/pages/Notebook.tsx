import { useState, useEffect, useCallback, type DragEvent, type ChangeEvent } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getNotebook,
  updateNotebook,
  deleteNotebook,
  removeArticleFromNotebook,
  getArticles,
  getArticle,
  analyzeArticle,
  startSearch,
  getJob,
} from "@/services/api";
import type { Article, ArticleFilters, SearchJob, SourceDatabase } from "@/types";
import ProgressIndicator from "@/components/ProgressIndicator/ProgressIndicator";
import ArticleCard from "@/components/ArticleCard/ArticleCard";
import ArticleDetail from "@/pages/ArticleDetail";
import MathText from "@/components/MathText/MathText";
import "./Notebook.css";

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export default function Notebook() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language.slice(0, 2);
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const notebookId = Number(id);
  const DEFAULT_INLINE_QUERY = "water dissociation recombination electromembrane bipolar membrane transport";

  // ─── Header state ───
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [editedTitle, setEditedTitle] = useState("");

  // ─── Panel collapse state ───
  const [sourcesOpen, setSourcesOpen] = useState(true);
  const [studioOpen, setStudioOpen] = useState(true);

  // ─── Search workspace state ───
  const [showAddFiles, setShowAddFiles] = useState(false);
  const [droppedFiles, setDroppedFiles] = useState<File[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const [activeJobId, setActiveJobId] = useState<number | null>(null);
  const [useJobFallback, setUseJobFallback] = useState(false);
  // inline search
  const [inlineQuery, setInlineQuery] = useState(DEFAULT_INLINE_QUERY);
  const SOURCES_ALL: { id: SourceDatabase; label: string; disabled?: boolean }[] = [
    { id: "arxiv",    label: "arXiv" },
    { id: "elibrary", label: "eLIBRARY" },
    { id: "scopus",   label: "Scopus",  disabled: true },
    { id: "wos",      label: "WOS",     disabled: true },
  ];
  const [activeSources, setActiveSources] = useState<SourceDatabase[]>(["arxiv", "elibrary"]);
  const MAX_PER_SOURCE = 10;
  const [selectedArticleId, setSelectedArticleId] = useState<number | null>(null);
  const [searchText, setSearchText] = useState("");
  const [filters, setFilters] = useState<ArticleFilters>({});
  const [allArticles, setAllArticles] = useState<Article[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  const debouncedSearch = useDebounce(searchText, 300);

  // Reset UI state when switching between notebooks so each one opens cleanly.
  useEffect(() => {
    setIsEditingTitle(false);
    setEditedTitle("");
    setShowAddFiles(false);
    setDroppedFiles([]);
    setIsDragOver(false);
    setActiveJobId(null);
    setUseJobFallback(false);
    setSelectedArticleId(null);
    setSearchText("");
    setFilters({});
    setAllArticles([]);
    setCurrentPage(1);
    setInlineQuery(DEFAULT_INLINE_QUERY);
  }, [notebookId]);

  // ─── Fetch notebook metadata ───
  const { data: notebook, isLoading, error } = useQuery({
    queryKey: ["notebook", id],
    queryFn: () => getNotebook(notebookId),
    enabled: !!id,
  });

  // ─── Articles from this notebook (filtered + paginated via ArticleFilter) ───
  const mergedFilters: ArticleFilters = {
    ...filters,
    notebook: notebookId,
    search: debouncedSearch || undefined,
    page: currentPage,
  };

  const { data: articlesData, isLoading: articlesLoading } = useQuery({
    queryKey: ["notebook-articles", notebookId, mergedFilters],
    queryFn: () => getArticles(mergedFilters),
    enabled: !!id && !useJobFallback,
  });

  useEffect(() => {
    if (!articlesData) return;
    if (currentPage === 1) {
      setAllArticles(articlesData.results);
    } else {
      setAllArticles((prev) => [...prev, ...articlesData.results]);
    }
  }, [articlesData, currentPage]);

  // Reset filters when search text changes
  useEffect(() => {
    setCurrentPage(1);
    setAllArticles([]);
    setUseJobFallback(false);
  }, [debouncedSearch]);

  // ─── Polling active search job ───
  const { data: job } = useQuery<SearchJob>({
    queryKey: ["job", activeJobId],
    queryFn: () => getJob(activeJobId!),
    enabled: activeJobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "running" || status === "pending" ? 2000 : false;
    },
  });

  // When job completes, refresh notebook articles
  useEffect(() => {
    if (job?.status === "completed") {
      setCurrentPage(1);
      setAllArticles([]);
      setUseJobFallback(false);
      queryClient.invalidateQueries({ queryKey: ["notebook", id] });
      queryClient.invalidateQueries({ queryKey: ["notebook-articles", notebookId] });
    }
  }, [job?.status, id, notebookId, queryClient]);

  // On initial load, always use notebook-articles query
  useEffect(() => {
    if (!notebook) return;
    setUseJobFallback(false);
  }, [notebook]);

  // ─── Fetch selected article detail for Studio panel ───
  const { data: selectedArticle } = useQuery({
    queryKey: ["article", String(selectedArticleId)],
    queryFn: () => getArticle(selectedArticleId!),
    enabled: selectedArticleId !== null && selectedArticleId > 0,
  });

  const analyzeMutation = useMutation({
    mutationFn: () => analyzeArticle(selectedArticleId!),
    onSuccess: (data) => {
      queryClient.setQueryData(["article", String(selectedArticleId)], data);
    },
    onError: (error: Error) => {
      alert(t("article.analyze_error", { message: error.message }));
    },
  });

  // ─── Mutations ───
  const updateMutation = useMutation({
    mutationFn: ({ title, description }: { title: string; description: string }) =>
      updateNotebook(notebookId, { title, description }),
    onSuccess: (data) => {
      setIsEditingTitle(false);
      queryClient.setQueryData(["notebook", id], data);
      queryClient.invalidateQueries({ queryKey: ["notebooks"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteNotebook(notebookId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notebooks"] });
      navigate("/");
    },
  });

  const removeMutation = useMutation({
    mutationFn: (articleId: number) => removeArticleFromNotebook(notebookId, articleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notebook", id] });
      queryClient.invalidateQueries({ queryKey: ["notebook-articles", notebookId] });
    },
  });

  const searchMutation = useMutation({
    mutationFn: startSearch,
    onSuccess: (newJob) => {
      setActiveJobId(newJob.id);
    },
  });

  // ─── Handlers ───
  const handleSaveTitle = () => {
    if (editedTitle.trim() && notebook) {
      updateMutation.mutate({ title: editedTitle, description: notebook.description || "" });
    } else {
      setIsEditingTitle(false);
    }
  };

  const handleDeleteNotebook = () => {
    if (window.confirm(t("confirm_delete"))) deleteMutation.mutate();
  };

  const handleInlineSearch = () => {
    if (!inlineQuery.trim() || activeSources.length === 0) return;
    setCurrentPage(1);
    setAllArticles([]);
    setUseJobFallback(false);
    setSelectedArticleId(null);
    searchMutation.mutate({
      query: inlineQuery,
      sources: activeSources,
      max_per_source: MAX_PER_SOURCE,
      notebook_id: notebookId,
    });
  };

  const toggleSource = (src: SourceDatabase) => {
    setActiveSources((prev) =>
      prev.includes(src) ? prev.filter((s) => s !== src) : [...prev, src]
    );
  };

  const handleDeleteArticle = useCallback(async (articleId: number) => {
    removeMutation.mutate(articleId);
    if (selectedArticleId === articleId) setSelectedArticleId(null);
  }, [selectedArticleId, removeMutation]);

  const updateFilters = (newFilters: Partial<ArticleFilters>) => {
    setCurrentPage(1);
    setAllArticles([]);
    setUseJobFallback(false);
    setFilters((f) => ({ ...f, ...newFilters }));
  };

  const isSearching = searchMutation.isPending || job?.status === "running" || job?.status === "pending";
  const hasMore = useJobFallback ? false : !!articlesData?.next;
  const totalCount = useJobFallback ? allArticles.length : articlesData?.count ?? 0;

  // ─── File drop handlers ───
  const handleDragOver = (e: DragEvent<HTMLDivElement>) => { e.preventDefault(); setIsDragOver(true); };
  const handleDragLeave = () => setIsDragOver(false);
  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length) setDroppedFiles((prev) => [...prev, ...files]);
  };
  const handleFileInput = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length) setDroppedFiles((prev) => [...prev, ...files]);
  };

  // ─── Derived: selected article title for studio ───
  const selectedTitle = selectedArticle
    ? (lang === "es" && selectedArticle.title_es ? selectedArticle.title_es
      : lang === "ru" && (selectedArticle.title_ru || selectedArticle.title) ? (selectedArticle.title_ru || selectedArticle.title)
      : lang === "en" && selectedArticle.title_en ? selectedArticle.title_en
      : selectedArticle.title)
    : "";

  // ─── Loading / Error states ───
  if (isLoading) {
    return (
      <div className="nb-page">
        <div className="nb-page__loading">{t("common.loading")}</div>
      </div>
    );
  }

  if (error || !notebook) {
    return (
      <div className="nb-page">
        <div className="nb-page__error">
          {t("common.not_found")}
          <button onClick={() => navigate("/")} className="nb-page__back-btn">
            {t("common.back")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="nb-page">
      {/* ─── Header ─── */}
      <div className="nb-header">
        <button onClick={() => navigate("/")} className="nb-header__back" title={t("common.back")}>
          ←
        </button>
        <div className="nb-header__title-section">
          {isEditingTitle ? (
            <div className="nb-header__title-edit">
              <input
                type="text"
                value={editedTitle}
                onChange={(e) => setEditedTitle(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSaveTitle();
                  if (e.key === "Escape") setIsEditingTitle(false);
                }}
                autoFocus
                className="nb-header__title-input"
              />
              <button onClick={handleSaveTitle} disabled={updateMutation.isPending} className="nb-header__title-save">
                ✓
              </button>
            </div>
          ) : (
            <h1
              className="nb-header__title"
              onDoubleClick={() => {
                setEditedTitle(notebook.title);
                setIsEditingTitle(true);
              }}
              title={t("notebook.click_to_rename")}
            >
              {notebook.title}
            </h1>
          )}
        </div>
        <button onClick={handleDeleteNotebook} disabled={deleteMutation.isPending} className="nb-header__delete" title={t("delete")}>
          🗑️
        </button>
      </div>

      {/* ─── Three-panel workspace ─── */}
      <div className={`nb-workspace${!sourcesOpen ? " nb-workspace--sources-closed" : ""}${!studioOpen ? " nb-workspace--studio-closed" : ""}`}>

        {/* ═══ LEFT: Sources panel ═══ */}
        <aside className={`nb-panel nb-sources${sourcesOpen ? "" : " nb-panel--collapsed"}`}>
          <div className="nb-panel__header" onClick={() => setSourcesOpen(!sourcesOpen)}>
            <span className={`nb-panel__toggle ${sourcesOpen ? "nb-panel__toggle--open" : ""}`}>‹</span>
            <h2 className="nb-panel__title">{t("notebook.sources")}</h2>
            <span className="nb-sources__count">{totalCount}</span>
          </div>

          {sourcesOpen && (
            <div className="nb-panel__body">
              {/* ─── + Añadir fuentes ─── */}
              <button
                className="nb-sources__add-btn"
                onClick={() => setShowAddFiles(!showAddFiles)}
              >
                <span>＋</span> {t("notebook.add_source")}
              </button>

              {/* ─── Drop zone ─── */}
              {showAddFiles && (
                <div
                  className={`nb-sources__dropzone${isDragOver ? " nb-sources__dropzone--over" : ""}`}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  onClick={() => document.getElementById("nb-file-input")?.click()}
                >
                  <input
                    id="nb-file-input"
                    type="file"
                    multiple
                    accept=".pdf,.txt,.doc,.docx,.png,.jpg,.jpeg,.mp3,.mp4,.wav"
                    style={{ display: "none" }}
                    onChange={handleFileInput}
                  />
                  <div className="nb-sources__dropzone-icon">📎</div>
                  <p className="nb-sources__dropzone-title">{t("notebook.drop_or_click")}</p>
                  <p className="nb-sources__dropzone-hint">{t("notebook.drop_formats")}</p>
                  {droppedFiles.length > 0 && (
                    <ul className="nb-sources__dropped-list">
                      {droppedFiles.map((f, i) => (
                        <li key={i} className="nb-sources__dropped-item">
                          <span>📄 {f.name}</span>
                          <button
                            onClick={(e) => { e.stopPropagation(); setDroppedFiles((prev) => prev.filter((_, j) => j !== i)); }}
                            className="nb-sources__dropped-remove"
                          >✕</button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {/* ─── Inline search ─── */}
              <div className="nb-inline-search">
                <div className="nb-inline-search__input-row">
                  <span className="nb-inline-search__icon">🔍</span>
                  <input
                    type="text"
                    className="nb-inline-search__input"
                    placeholder={t("notebook.search_placeholder")}
                    value={inlineQuery}
                    onChange={(e) => setInlineQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleInlineSearch()}
                  />
                </div>
                <div className="nb-inline-search__chips-row">
                  {SOURCES_ALL.map(({ id: src, label, disabled }) => (
                    <button
                      key={src}
                      disabled={!!disabled}
                      className={`nb-chip${
                        disabled ? " nb-chip--disabled" : activeSources.includes(src) ? " nb-chip--active" : ""
                      }`}
                      onClick={() => !disabled && toggleSource(src)}
                      title={disabled ? t("search.coming_soon") : label}
                    >
                      {label}
                    </button>
                  ))}
                  <button
                    className="nb-inline-search__go"
                    disabled={isSearching || !inlineQuery.trim() || activeSources.length === 0}
                    onClick={handleInlineSearch}
                    title={t("search.submit")}
                  >
                    {isSearching ? "⋯" : "›"}
                  </button>
                </div>
              </div>

              {/* ─── Progress indicator ─── */}
              {job && <div className="nb-sources__progress"><ProgressIndicator job={job} /></div>}

              {/* Filters */}
              <div className="nb-sources__filters">
                <input
                  type="text"
                  placeholder={t("search.filter_text")}
                  className="nb-sources__filter-input"
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                />
                <div className="nb-sources__filter-selects">
                  <select
                    className="nb-sources__select"
                    value={filters.source_db || ""}
                    onChange={(e) =>
                      updateFilters({ source_db: (e.target.value as SourceDatabase) || undefined })
                    }
                  >
                    <option value="">{t("search.filter_all_sources")}</option>
                    <option value="arxiv">arXiv</option>
                    <option value="elibrary">eLIBRARY</option>
                    <option value="scopus">Scopus</option>
                    <option value="wos">WOS</option>
                  </select>
                </div>
              </div>

              {/* Article list */}
              <div className="nb-sources__list">
                {articlesLoading && currentPage === 1 ? (
                  <p className="nb-sources__list-loading">{t("common.loading")}</p>
                ) : allArticles.length === 0 ? (
                  <div className="nb-sources__empty">
                    <p>{t("notebook.empty_hint")}</p>
                    <button className="nb-sources__empty-cta" onClick={() => { const el = document.querySelector<HTMLInputElement>(".nb-inline-search__input"); el?.focus(); }}>
                      {t("start_search")}
                    </button>
                  </div>
                ) : (
                  allArticles.map((article) => (
                    <ArticleCard
                      key={article.id}
                      article={article}
                      isSelected={article.id === selectedArticleId}
                      onSelect={() => setSelectedArticleId(article.id)}
                      onDelete={handleDeleteArticle}
                      showAuthors={false}
                    />
                  ))
                )}

                {hasMore && (
                  <div className="nb-sources__load-more">
                    <button
                      className="nb-sources__load-more-btn"
                      disabled={articlesLoading}
                      onClick={() => setCurrentPage((p) => p + 1)}
                    >
                      {articlesLoading
                        ? t("common.loading")
                        : t("search.load_more", { shown: allArticles.length, total: totalCount })}
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
        </aside>

        {/* ═══ CENTER: Detail panel ═══ */}
        <section className="nb-detail">
          <div className="nb-detail__scroll">
            {selectedArticleId ? (
              <ArticleDetail
                articleId={selectedArticleId}
                onClose={() => setSelectedArticleId(null)}
              />
            ) : (
              <div className="nb-detail__empty">
                <div className="nb-detail__empty-icon">📄</div>
                <h3>{t("notebook.select_source")}</h3>
                <p>{t("notebook.select_source_desc")}</p>
              </div>
            )}
          </div>
        </section>

        {/* ═══ RIGHT: Studio panel ═══ */}
        <aside className={`nb-panel nb-studio${studioOpen ? "" : " nb-panel--collapsed"}`}>
          <div className="nb-panel__header" onClick={() => setStudioOpen(!studioOpen)}>
            <h2 className="nb-panel__title">{t("notebook.studio")}</h2>
            <span className={`nb-panel__toggle ${studioOpen ? "nb-panel__toggle--open" : ""}`}>›</span>
          </div>

          {studioOpen && (
            <div className="nb-panel__body">
              {selectedArticle ? (
                <div className="nb-studio__content">
                  <div className="nb-studio__article-info">
                    <span className={`badge badge--${selectedArticle.source_db}`}>
                      {selectedArticle.source_db.toUpperCase()}
                    </span>
                    <h3 className="nb-studio__article-title">
                      <MathText text={selectedTitle} />
                    </h3>
                  </div>

                  {/* ─── AI Analysis tools ─── */}
                  <div className="nb-studio__section">
                    <h4 className="nb-studio__section-title">
                      <span className="nb-studio__section-icon">🤖</span>
                      {t("notebook.ai_tools")}
                    </h4>

                    <button
                      className="nb-studio__action-btn"
                      onClick={() => analyzeMutation.mutate()}
                      disabled={analyzeMutation.isPending}
                    >
                      <span className="nb-studio__action-icon">✨</span>
                      <span className="nb-studio__action-text">
                        {analyzeMutation.isPending
                          ? t("article.analyzing")
                          : selectedArticle.ai_processed
                            ? t("article.reanalyze")
                            : t("article.analyze")}
                      </span>
                      <span className="nb-studio__action-arrow">›</span>
                    </button>

                    {analyzeMutation.isPending && (
                      <p className="nb-studio__pending">{t("article.analyzing_bg")}</p>
                    )}

                    {selectedArticle.ai_processed && (
                      <p className="nb-studio__done">✅ {t("article.ai_processed_label")}</p>
                    )}
                  </div>
                </div>
              ) : (
                <div className="nb-studio__empty">
                  <div className="nb-studio__empty-icon">🤖</div>
                  <p>{t("notebook.select_to_analyze")}</p>
                </div>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
