import React, { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getNotebooks, createNotebook, deleteNotebook } from "@/services/api";
import type { Notebook } from "@/types";
import "./Home.css";

export default function Home() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["notebooks"],
    queryFn: getNotebooks,
    retry: 2,
    retryDelay: 3000,
  });

  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (showCreate) inputRef.current?.focus();
  }, [showCreate]);

  const createMutation = useMutation({
    mutationFn: (title: string) => createNotebook(title),
    onSuccess: (nb) => {
      queryClient.invalidateQueries({ queryKey: ["notebooks"] });
      navigate(`/notebooks/${nb.id}`);
    },
  });

  const handleOpenCreate = () => {
    setNewTitle("");
    setShowCreate(true);
  };

  const handleConfirmCreate = () => {
    const title = newTitle.trim() || t("notebook_title_placeholder");
    createMutation.mutate(title);
    setShowCreate(false);
  };

  const handleCreateKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleConfirmCreate();
    if (e.key === "Escape") { setShowCreate(false); setNewTitle(""); }
  };

  const deleteMutation = useMutation({
    mutationFn: deleteNotebook,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notebooks"] });
    },
  });

  const handleDelete = (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    if (window.confirm(t("confirm_delete"))) {
      deleteMutation.mutate(id);
    }
  };

  const notebooks: Notebook[] = data?.results ?? [];

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  };

  return (
    <div className="home">
      <div className="home__header">
        <h1 className="home__title">{t("home.title")}</h1>
        <p className="home__subtitle">{t("home.subtitle")}</p>
      </div>

      <div className="home__grid">
        {/* Create new notebook card */}
        {showCreate ? (
          <div className="home__card home__card--create home__card--creating">
            <div className="home__card-create-icon">📓</div>
            <input
              ref={inputRef}
              className="home__card-create-input"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={handleCreateKeyDown}
              placeholder={t("notebook_title_placeholder")}
              maxLength={120}
            />
            <div className="home__card-create-actions">
              <button
                className="home__card-create-confirm"
                onClick={handleConfirmCreate}
                disabled={createMutation.isPending}
              >
                {createMutation.isPending ? t("creating") : t("create")}
              </button>
              <button
                className="home__card-create-cancel"
                onClick={() => { setShowCreate(false); setNewTitle(""); }}
              >
                {t("cancel")}
              </button>
            </div>
          </div>
        ) : (
          <button
            className="home__card home__card--create"
            onClick={handleOpenCreate}
            disabled={createMutation.isPending}
          >
            <div className="home__card-create-icon">＋</div>
            <span className="home__card-create-label">
              {createMutation.isPending ? t("creating") : t("home.new_notebook")}
            </span>
          </button>
        )}

        {/* Existing notebooks */}
        {notebooks.map((nb) => (
          <div
            key={nb.id}
            className="home__card"
            onClick={() => navigate(`/notebooks/${nb.id}`)}
          >
            <div className="home__card-icon">📓</div>
            <div className="home__card-body">
              <h3 className="home__card-title">{nb.title}</h3>
              <p className="home__card-meta">
                {nb.articles_count ?? 0} {(nb.articles_count ?? 0) === 1 ? t("home_article_singular") : t("home_article_plural")}
                {" · "}
                {formatDate(nb.created_at)}
              </p>
              {nb.description && (
                <p className="home__card-desc">{nb.description}</p>
              )}
            </div>
            <button
              className="home__card-delete"
              onClick={(e) => handleDelete(e, nb.id)}
              title={t("delete")}
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      {isLoading && (
        <div className="home__loading">{t("common.loading")}</div>
      )}

      {isError && (
        <div className="home__error">
          <div className="home__empty-icon">⚠️</div>
          <p className="home__empty-text">{t("common.api_error")}</p>
          <p style={{ fontSize: "0.85rem", color: "#999", marginTop: 4 }}>
            {(error as Error)?.message || t("common.unknown_error")}
          </p>
          <button
            className="home__card-create-confirm"
            style={{ marginTop: 12 }}
            onClick={() => refetch()}
          >
            {t("common.retry")}
          </button>
        </div>
      )}

      {!isLoading && !isError && notebooks.length === 0 && (
        <div className="home__empty">
          <div className="home__empty-icon">📚</div>
          <p className="home__empty-text">{t("home.empty")}</p>
        </div>
      )}
    </div>
  );
}
