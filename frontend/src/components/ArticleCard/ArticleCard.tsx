import React, { useState, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import type { Article } from "@/types";
import MathText from "@/components/MathText/MathText";
import "./ArticleCard.css";

interface ArticleCardProps {
  article: Article;
  isSelected?: boolean;
  onSelect?: () => void;
  onDelete?: (id: number) => void;
  onRename?: (id: number, newTitle: string) => void;
  showAuthors?: boolean;
}

function formatAuthors(authors: string): string {
  const parts = authors.split(",").map((a) => a.trim()).filter(Boolean);
  if (parts.length <= 3) return parts.join(", ");
  return `${parts.slice(0, 3).join(", ")} et al.`;
}

export default function ArticleCard({ article, isSelected = false, onSelect, onDelete, onRename, showAuthors = true }: ArticleCardProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language.slice(0, 2);
  const [menuOpen, setMenuOpen] = useState(false);
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);

  // Close menu on outside click
  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  // Focus rename input on open
  useEffect(() => {
    if (isRenaming) renameInputRef.current?.focus();
  }, [isRenaming]);

  const displayTitle =
    lang === "es" && article.title_es
      ? article.title_es
      : lang === "ru" && (article.title_ru || article.title)
        ? article.title_ru || article.title
        : lang === "en" && article.title_en
          ? article.title_en
          : article.title;

  const handleMenuClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setMenuOpen((prev) => !prev);
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    setMenuOpen(false);
    if (onDelete && confirm(t("article.confirm_delete"))) {
      onDelete(article.id);
    }
  };

  const handleRenameStart = (e: React.MouseEvent) => {
    e.stopPropagation();
    setMenuOpen(false);
    setRenameValue(displayTitle);
    setIsRenaming(true);
  };

  const handleRenameSubmit = () => {
    const trimmed = renameValue.trim();
    if (trimmed && trimmed !== displayTitle && onRename) {
      onRename(article.id, trimmed);
    }
    setIsRenaming(false);
  };

  const handleRenameKeyDown = (e: React.KeyboardEvent) => {
    e.stopPropagation();
    if (e.key === "Enter") handleRenameSubmit();
    if (e.key === "Escape") setIsRenaming(false);
  };

  return (
    <article
      className={`article-card article-card--${article.source_db}${isSelected ? " article-card--selected" : ""}`}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onSelect?.(); }}
    >
      <div className="article-card__accent" />
      <div className="article-card__body">
        <div className="article-card__header">
          <span className={`badge badge--${article.source_db}`}>
            {article.source_db.toUpperCase()}
          </span>
          {article.language_original && (
            <span className="article-card__lang">
              {article.language_original.toUpperCase()}
            </span>
          )}
          {article.ai_processed && (
            <span className="article-card__ai-badge" title={t("article.ai_processed")}>
              ✨ IA
            </span>
          )}
          {article.year && (
            <span className="article-card__year">{article.year}</span>
          )}

          {/* 3-dot menu */}
          <div className="article-card__menu-wrap" ref={menuRef}>
            <button
              className="article-card__menu-btn"
              onClick={handleMenuClick}
              title={t("article.more_options")}
              aria-label={t("article.more_options")}
            >
              ⋮
            </button>
            {menuOpen && (
              <div className="article-card__dropdown">
                <button className="article-card__dropdown-item" onClick={handleRenameStart}>
                  ✏️ {t("article.rename")}
                </button>
                <button className="article-card__dropdown-item article-card__dropdown-item--danger" onClick={handleDelete}>
                  🗑️ {t("article.delete")}
                </button>
              </div>
            )}
          </div>
        </div>

        {isRenaming ? (
          <input
            ref={renameInputRef}
            className="article-card__rename-input"
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onBlur={handleRenameSubmit}
            onKeyDown={handleRenameKeyDown}
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <h3 className="article-card__title">
            <MathText text={displayTitle} />
          </h3>
        )}

        {showAuthors && article.authors && (
          <p className="article-card__authors">
            {formatAuthors(article.authors)}
          </p>
        )}
      </div>
    </article>
  );
}
