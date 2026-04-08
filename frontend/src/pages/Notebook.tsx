import { useState, useEffect, useCallback, useRef, type DragEvent, type ChangeEvent } from "react";
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
  getAnalyzeStatus,
  startSearch,
  getJob,
  renameArticle,
  uploadFileToNotebook,
} from "@/services/api";
import type { Article, ArticleFilters, SearchJob, SourceDatabase } from "@/types";
import { useToast } from "@/components/Toast/ToastContext";
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
  const isValidId = !!id && !Number.isNaN(notebookId) && notebookId > 0;
  const DEFAULT_INLINE_QUERY = "water dissociation recombination electromembrane bipolar membrane transport";

  // Redirect to home if the notebook ID in the URL is invalid (e.g. /notebooks/undefined)
  useEffect(() => {
    if (!isValidId) {
      navigate("/", { replace: true });
    }
  }, [isValidId, navigate]);

  // ─── Header state ───
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [editedTitle, setEditedTitle] = useState("");

  // ─── Panel collapse state ───
  const [sourcesOpen, setSourcesOpen] = useState(true);
  const [studioOpen, setStudioOpen] = useState(true);

  // ─── Search workspace state ───
  const [showAddFiles, setShowAddFiles] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [activeJobId, setActiveJobId] = useState<number | null>(null);
  const [useJobFallback, setUseJobFallback] = useState(false);
  const [inlineQuery, setInlineQuery] = useState(DEFAULT_INLINE_QUERY);
  const SOURCES_ALL: { id: SourceDatabase; label: string; disabled?: boolean }[] = [
    { id: "arxiv",    label: "arXiv" },
    { id: "elibrary", label: "eLIBRARY" },
    { id: "scopus",   label: "Scopus" },
    { id: "wos",      label: "WOS" },
  ];
  const [activeSources, setActiveSources] = useState<SourceDatabase[]>(["arxiv", "elibrary", "scopus", "wos"]);
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
    enabled: isValidId,
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
    enabled: isValidId && !useJobFallback,
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

  const toast = useToast();
  const analyzeToastRef = useRef<string | null>(null);
  const [analyzingArticleId, setAnalyzingArticleId] = useState<number | null>(null);
  const analyzeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startAnalyzeTimerRef = useRef<((articleId: number) => void) | null>(null);

  const analyzeMutation = useMutation({
    mutationFn: (force: boolean) => analyzeArticle(selectedArticleId!, force),
    onSuccess: () => {
      setAnalyzingArticleId(selectedArticleId);
      analyzeToastRef.current = toast.loading(t("article.analyzing_bg"));
    },
    onError: (error: Error) => {
      toast.error(t("article.analyze_error", { message: error.message }));
    },
  });

  // ─── Polling analyze status ───
  const ANALYZE_POLL_TIMEOUT = 300_000; // 5 min = mismo que django-q2 timeout

  const { data: analyzeStatus } = useQuery({
    queryKey: ["analyze-status", analyzingArticleId],
    queryFn: () => getAnalyzeStatus(analyzingArticleId!),
    enabled: analyzingArticleId !== null,
    refetchInterval: (query) => {
      const st = query.state.data?.status;
      return st === "processing" || !st ? 3000 : false;
    },
  });

  // Timer recursivo: watchdog que se reinicia cada 5 min mientras ai_processing=true
  // Borde 1: Si cambia de artículo, limpia el timer anterior
  // Borde 2: Distingue "fallo de fetch" (transitorio) de "realmente no completado"
  useEffect(() => {
    startAnalyzeTimerRef.current = (articleId: number) => {
      if (analyzeTimerRef.current) {
        clearTimeout(analyzeTimerRef.current);
      }

      analyzeTimerRef.current = setTimeout(async () => {
        try {
          const response = await fetch(`/api/articles/${articleId}/`);

          if (!response.ok) {
            console.warn(`[AnalyzeTimer] HTTP ${response.status}, reintentando...`);
            startAnalyzeTimerRef.current?.(articleId);
            return;
          }

          const article = await response.json();

          if (article.ai_processed) {
            if (analyzeToastRef.current) {
              toast.update(analyzeToastRef.current, t("article.ai_processed_label"), "success", 4000);
              analyzeToastRef.current = null;
            }
            queryClient.setQueryData(["article", String(articleId)], article);
            queryClient.invalidateQueries({ queryKey: ["notebook-articles", notebookId] });
            setAnalyzingArticleId(null);
          } else if (article.ai_processing) {
            console.warn(`[AnalyzeTimer] Aún procesando artículo ${articleId}, reintentando en 5 min`);
            startAnalyzeTimerRef.current?.(articleId);
          } else {
            if (analyzeToastRef.current) {
              toast.update(analyzeToastRef.current, t("toast.timeout"), "error", 8000);
              analyzeToastRef.current = null;
            }
            queryClient.invalidateQueries({ queryKey: ["article", String(articleId)] });
            setAnalyzingArticleId(null);
          }
        } catch (err) {
          console.warn("[AnalyzeTimer] Error de red, reintentando...", err);
          startAnalyzeTimerRef.current?.(articleId);
        }
      }, ANALYZE_POLL_TIMEOUT);
    };
  });

  // Iniciar timer cuando cambia de artículo
  useEffect(() => {
    if (analyzingArticleId) {
      startAnalyzeTimerRef.current?.(analyzingArticleId);
    }
    return () => {
      if (analyzeTimerRef.current) {
        clearTimeout(analyzeTimerRef.current);
        analyzeTimerRef.current = null;
      }
    };
  }, [analyzingArticleId]);

  useEffect(() => {
    if (!analyzeStatus || !analyzingArticleId) return;

    if (analyzeStatus.status === "completed") {
      // Dismiss loading toast and show success
      if (analyzeToastRef.current) {
        toast.update(analyzeToastRef.current, t("article.ai_processed_label"), "success", 4000);
        analyzeToastRef.current = null;
      }
      // Update article data in cache
      if (analyzeStatus.article) {
        queryClient.setQueryData(["article", String(analyzingArticleId)], analyzeStatus.article);
      }
      queryClient.invalidateQueries({ queryKey: ["notebook-articles", notebookId] });
      setAnalyzingArticleId(null);
    } else if (analyzeStatus.status === "failed") {
      const errorMsg = analyzeStatus.error_code === "rate_limited"
        ? t("toast.rate_limited")
        : analyzeStatus.error_code === "auth_error"
          ? t("toast.auth_error")
          : analyzeStatus.error_code === "timeout"
            ? t("toast.timeout")
            : t("article.analyze_error", { message: analyzeStatus.error || t("common.unknown_error") });
      if (analyzeToastRef.current) {
        toast.update(analyzeToastRef.current, errorMsg, "error", 8000);
        analyzeToastRef.current = null;
      }
      // Refresh article to show error state
      queryClient.invalidateQueries({ queryKey: ["article", String(analyzingArticleId)] });
      setAnalyzingArticleId(null);
    }
  }, [analyzeStatus, analyzingArticleId, queryClient, notebookId, toast, t]);

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

  const handleRenameArticle = useCallback(async (articleId: number, newTitle: string) => {
    try {
      const updatedArticle = await renameArticle(articleId, newTitle);

      queryClient.setQueryData(["article", String(articleId)], updatedArticle);

      queryClient.setQueryData(
        ["notebook-articles", notebookId, mergedFilters],
        (old: any) => {
          if (!old) return old;
          return {
            ...old,
            results: old.results.map((a: Article) =>
              a.id === articleId ? { ...a, ...updatedArticle } : a
            ),
          };
        }
      );

      setAllArticles((prev) =>
        prev.map((a) => (a.id === articleId ? { ...a, ...updatedArticle } : a))
      );

      toast.success(t("common.saved"));
    } catch (err: any) {
      toast.error(t("common.error", { message: err.message }));
    }
  }, [notebookId, mergedFilters, queryClient, toast, t]);

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
  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => setIsDragOver(false);

  const handleDrop = async (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    const files = Array.from(e.dataTransfer.files);
    if (!files.length) return;

    const loadingId = toast.loading(t("notebook.uploading_files"));

    for (const file of files) {
      try {
        const article = await uploadFileToNotebook(notebookId, file);
        toast.success(t("notebook.file_uploaded", { name: file.name }));
        setAllArticles((prev) => [article, ...prev]);
      } catch (error: any) {
        const msg = error?.response?.data?.detail || error.message;
        toast.error(t("notebook.upload_error", { name: file.name, error: msg }));
      }
    }

    toast.dismiss(loadingId);
    queryClient.invalidateQueries({ queryKey: ["notebook-articles", notebookId] });
    queryClient.invalidateQueries({ queryKey: ["notebook", id] });
  };

  const handleFileInput = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;

    // Reset input so the same file can be selected again
    e.target.value = "";

    const loadingId = toast.loading(t("notebook.uploading_files"));

    for (const file of files) {
      try {
        const article = await uploadFileToNotebook(notebookId, file);
        toast.success(t("notebook.file_uploaded", { name: file.name }));
        setAllArticles((prev) => [article, ...prev]);
      } catch (error: any) {
        const msg = error?.response?.data?.detail || error.message;
        toast.error(t("notebook.upload_error", { name: file.name, error: msg }));
      }
    }

    toast.dismiss(loadingId);
    queryClient.invalidateQueries({ queryKey: ["notebook-articles", notebookId] });
    queryClient.invalidateQueries({ queryKey: ["notebook", id] });
  };

  // ─── Derived: selected article title for studio ───
  const selectedTitle = selectedArticle
    ? lang === "es" && selectedArticle.title_es
      ? selectedArticle.title_es
      : lang === "ru" && (selectedArticle.title_ru || selectedArticle.title)
        ? selectedArticle.title_ru || selectedArticle.title
        : lang === "en" && selectedArticle.title_en
          ? selectedArticle.title_en
          : selectedArticle.title
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
      <div
        className={`nb-workspace${!sourcesOpen ? " nb-workspace--sources-closed" : ""}${
          !studioOpen ? " nb-workspace--studio-closed" : ""
        }`}
      >

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
                    accept=".pdf,.txt,.doc,.docx,.md,.tex,.rtf"
                    style={{ display: "none" }}
                    onChange={handleFileInput}
                  />
                  <div className="nb-sources__dropzone-icon">📎</div>
                  <p className="nb-sources__dropzone-title">{t("notebook.drop_or_click")}</p>
                  <p className="nb-sources__dropzone-hint">{t("notebook.drop_formats")}</p>
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
              {job && (
                <div className="nb-sources__progress">
                  <ProgressIndicator job={job} />
                </div>
              )}

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
                    <option value="file">📄 {t("notebook.uploaded_files") || "Files"}</option>
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
                      onRename={handleRenameArticle}
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
                    <span className={`badge badge--${selectedArticle.source_db || ""}`}>
                      {selectedArticle.source_db?.toUpperCase() || ""}
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
                      onClick={() =>
                        analyzeMutation.mutate(!!selectedArticle.ai_processed)
                      }
                      disabled={
                        analyzeMutation.isPending ||
                        selectedArticle.ai_processing ||
                        analyzingArticleId === selectedArticle.id
                      }
                    >
                      {(selectedArticle.ai_processing || analyzingArticleId === selectedArticle.id) ? (
                        <span className="nb-studio__action-spinner" />
                      ) : (
                        <span className="nb-studio__action-icon">✨</span>
                      )}
                      <span className="nb-studio__action-text">
                        {(selectedArticle.ai_processing || analyzingArticleId === selectedArticle.id)
                          ? t("article.analyzing")
                          : analyzeMutation.isPending
                            ? t("article.analyzing")
                            : selectedArticle.ai_processed
                              ? t("article.reanalyze")
                              : t("article.analyze")}
                      </span>
                      <span className="nb-studio__action-arrow">›</span>
                    </button>

                    {(selectedArticle.ai_processing || analyzingArticleId === selectedArticle.id) && (
                      <p className="nb-studio__pending">{t("article.analyzing_bg")}</p>
                    )}

                    {selectedArticle.ai_processed && !selectedArticle.ai_processing && (
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
