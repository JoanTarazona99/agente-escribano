/**
 * Fixtures de prueba — datos mockeados sin dependencia de MSW.
 * Importar desde aquí en tests unitarios de componentes.
 */
import type { Article, SearchJob } from "@/types";

export const mockArticle: Article = {
  id: 1,
  title: "Water dissociation in bipolar ion-exchange membranes",
  title_es: "Disociación del agua en membranas bipolares",
  title_en: "Water dissociation in bipolar ion-exchange membranes",
  title_ru: "Диссоциация воды в биполярных ионообменных мембранах",
  authors: "Ivanov, A.B.; Petrov, C.D.",
  year: 2023,
  journal: "Journal of Membrane Science",
  doi: "10.1016/j.memsci.2023.00001",
  doi_url: "https://doi.org/10.1016/j.memsci.2023.00001",
  has_doi: true,
  url: "https://arxiv.org/abs/2301.00001",
  source_db: "arxiv",
  article_type: "experimental",
  ai_processed: true,
  language_original: "en",
  created_at: "2026-03-19T10:00:00Z",
  abstract_original: "Study of water dissociation in bipolar membranes under electric field.",
  abstract_es: "Estudio de disociación del agua en membranas bipolares.",
  abstract_en: "Study of water dissociation in bipolar membranes under electric field.",
  ai_summary: "Данное экспериментальное исследование анализирует диссоциацию воды в биполярных мембранах.",
  ai_summary_es: "Este estudio experimental analiza la disociación del agua en membranas bipolares.",
  ai_summary_en: "This experimental study analyzes water dissociation in bipolar membranes.",
  ai_summary_ru: "Данное экспериментальное исследование анализирует диссоциацию воды в биполярных мембранах.",
  ai_analysis: "1. ТИП: Экспериментальная\n2. МЕТОДОЛОГИЯ: Циклическая вольтамперометрия\n3. РЕЛЕВАНТНОСТЬ: Высокая",
  ai_analysis_es: "1. TIPO: Experimental\n2. METODOLOGÍA: Voltametría cíclica\n3. RELEVANCIA: Alta",
  ai_analysis_en: "1. TYPE: Experimental\n2. METHODOLOGY: Cyclic voltammetry\n3. RELEVANCE: High",
  ai_analysis_ru: "1. ТИП: Экспериментальная\n2. МЕТОДОЛОГИЯ: Циклическая вольтамперометрия\n3. РЕЛЕВАНТНОСТЬ: Высокая",
  keywords: "water dissociation, bipolar membrane, electromembrane",
};

export const mockJob: SearchJob = {
  id: 1,
  query: "water dissociation electromembrane",
  sources: "arxiv,elibrary",
  status: "completed",
  total_found: 15,
  total_saved: 12,
  error_message: "",
  started_at: "2026-03-19T10:00:00Z",
  finished_at: "2026-03-19T10:01:30Z",
  notebook: null,
};
