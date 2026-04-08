/** Tipos TypeScript que reflejan los modelos Django. */

export type SourceDatabase = "scopus" | "wos" | "arxiv" | "elibrary" | "file" | "unknown";
export type ArticleType = "theoretical" | "experimental" | "review" | "mixed" | "unknown";

export interface Article {
  id: number;
  title: string;
  title_es: string;
  title_en: string;
  title_ru: string;
  authors: string;
  year: number | null;
  journal: string;
  doi: string | null;
  doi_url: string;
  has_doi: boolean;
  url: string;
  source_db: SourceDatabase;
  article_type: ArticleType;
  ai_processed: boolean;
  ai_processing: boolean;
  ai_error: string;
  ai_error_code: string;
  language_original: string;
  created_at: string;
  // Campos solo en detalle
  abstract_original?: string;
  abstract_es?: string;
  abstract_en?: string;
  abstract_ru?: string;
  keywords?: string;
  ai_summary?: string;
  ai_summary_es?: string;
  ai_summary_en?: string;
  ai_summary_ru?: string;
  ai_analysis?: string;
  ai_analysis_es?: string;
  ai_analysis_en?: string;
  ai_analysis_ru?: string;
  source_id?: string;
  full_text?: string;
  original_filename?: string;
  updated_at?: string;
}

export interface ArticleListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: Article[];
}

export type SearchJobStatus = "pending" | "running" | "completed" | "failed";

export interface SearchJob {
  id: number;
  query: string;
  sources: string;
  status: SearchJobStatus;
  total_found: number;
  total_saved: number;
  error_message: string;
  started_at: string;
  finished_at: string | null;
  notebook: number | null;
}

export interface SearchRequest {
  query?: string;
  sources?: SourceDatabase[];
  max_per_source?: number;
  notebook_id?: number;
}

export interface ArticleFilters {
  source_db?: SourceDatabase;
  article_type?: ArticleType;
  year?: number;
  ai_processed?: boolean;
  search?: string;
  page?: number;
  ordering?: string;
  job?: number;   // ID del SearchJob — muestra solo artículos de esa búsqueda
  notebook?: number; // ID del Notebook — muestra solo artículos de ese cuaderno
}

// ─── Notebook Types ───────────────────────────────────────────────

export interface Notebook {
  id: number;
  title: string;
  description: string;
  created_at: string;
  updated_at?: string;
  articles?: Article[];
  articles_count?: number;
}

export interface NotebookListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: Notebook[];
}

// ─── Analysis Status (polling) ────────────────────────────────────

export type AnalysisStatus = "queued" | "processing" | "completed" | "failed";

export interface AnalyzeStatusResponse {
  status: AnalysisStatus;
  article?: Article;
  error?: string;
  error_code?: string;
}

