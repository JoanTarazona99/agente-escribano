/**
 * Cliente HTTP para la API Django.
 * - Dev: Vite proxy /api/* → localhost:8000
 * - Prod: VITE_API_BASE_URL apunta directo al backend (CORS habilitado)
 */
import axios from "axios";
import type {
  Article,
  ArticleFilters,
  ArticleListResponse,
  SearchJob,
  SearchRequest,
  Notebook,
  NotebookListResponse,
} from "@/types";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api",
  timeout: 30_000, // 30s para tolerar cold-start de Render free tier
  headers: {
    "Content-Type": "application/json",
  },
});

/** Retry automático: reintenta 1 vez SOLO en GET con errores de red/timeout (cold-start).
 *  NUNCA reintenta POST/PUT/PATCH/DELETE para evitar crear duplicados. */
api.interceptors.response.use(undefined, async (error) => {
  const config = error.config;
  if (
    config &&
    !config.__retried &&
    config.method === "get" &&
    (!error.response || error.code === "ECONNABORTED" || error.code === "ERR_NETWORK")
  ) {
    config.__retried = true;
    await new Promise((r) => setTimeout(r, 2000));
    return api.request(config);
  }
  return Promise.reject(error);
});

/** Lanza una búsqueda asíncrona y devuelve el SearchJob creado. */
export async function startSearch(payload: SearchRequest): Promise<SearchJob> {
  const { data } = await api.post<SearchJob>("/search/", payload);
  return data;
}

/** Consulta el estado de un trabajo de búsqueda. */
export async function getJob(id: number): Promise<SearchJob> {
  const { data } = await api.get<SearchJob>(`/jobs/${id}/`);
  return data;
}

/** Lista artículos con filtros opcionales. */
export async function getArticles(filters: ArticleFilters = {}): Promise<ArticleListResponse> {
  const params = Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== undefined && v !== ""),
  );
  const { data } = await api.get<ArticleListResponse>("/articles/", { params });
  return data;
}

/** Obtiene el detalle completo de un artículo. */
export async function getArticle(id: number): Promise<Article> {
  const { data } = await api.get<Article>(`/articles/${id}/`);
  return data;
}

/** Lanza el análisis IA de un artículo. Con force=true regenera campos existentes. */
export async function analyzeArticle(id: number, force = false): Promise<Article> {
  const { data } = await api.post<Article>(
    `/articles/${id}/analyze/`,
    null,
    {
      params: force ? { force: "true" } : {},
      timeout: 180_000, // 3 min — el LLM puede tardar con traducciones
    },
  );
  return data;
}

/** Elimina un artículo. */
export async function deleteArticle(id: number): Promise<void> {
  await api.delete(`/articles/${id}/`);
}

/** Renombra (actualiza título) un artículo. */
export async function renameArticle(id: number, title: string): Promise<Article> {
  const { data } = await api.patch<Article>(`/articles/${id}/`, { title });
  return data;
}

/** Health check del sistema (Ollama, BD, stats). */
export interface HealthResponse {
  database: { ok: boolean; error?: string };
  ollama: { ok: boolean; model: string; available_models?: string[]; model_loaded?: boolean; error?: string };
  stats: { total_articles: number; ai_processed: number };
}

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>("/health/");
  return data;
}

// ─── Notebook API ──────────────────────────────────────────────────

/** Crea un nuevo cuaderno. */
export async function createNotebook(title?: string, description?: string): Promise<Notebook> {
  const { data } = await api.post<Notebook>("/notebooks/", {
    title: title || "Nuevo cuaderno",
    description: description || "",
  });
  return data;
}

/** Lista todos los cuadernos. */
export async function getNotebooks(): Promise<NotebookListResponse> {
  const { data } = await api.get<NotebookListResponse>("/notebooks/");
  return data;
}

/** Obtiene el detalle de un cuaderno. */
export async function getNotebook(id: number): Promise<Notebook> {
  const { data } = await api.get<Notebook>(`/notebooks/${id}/`);
  return data;
}

/** Actualiza un cuaderno. */
export async function updateNotebook(
  id: number,
  data: { title?: string; description?: string }
): Promise<Notebook> {
  const response = await api.patch<Notebook>(`/notebooks/${id}/`, data);
  return response.data;
}

/** Elimina un cuaderno. */
export async function deleteNotebook(id: number): Promise<void> {
  await api.delete(`/notebooks/${id}/`);
}

/** Agrega un artículo al cuaderno. */
export async function addArticleToNotebook(notebookId: number, articleId: number): Promise<Notebook> {
  const { data } = await api.post<Notebook>(`/notebooks/${notebookId}/add-article/${articleId}/`);
  return data;
}

/** Quita un artículo del cuaderno. */
export async function removeArticleFromNotebook(notebookId: number, articleId: number): Promise<Notebook> {
  const { data } = await api.post<Notebook>(`/notebooks/${notebookId}/remove-article/${articleId}/`);
  return data;
}

/** Busca artículos por texto (para añadir a cuaderno). */
export async function searchArticlesForNotebook(query: string): Promise<ArticleListResponse> {
  const { data } = await api.get<ArticleListResponse>("/articles/", {
    params: { search: query, page_size: 20 },
  });
  return data;
}

export default api;
