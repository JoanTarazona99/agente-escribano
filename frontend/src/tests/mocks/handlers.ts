/**
 * Handlers MSW — interceptan llamadas a /api/* en tests Jest y Playwright.
 */
import { http, HttpResponse } from "msw";
import type { ArticleListResponse } from "@/types";
import { mockArticle, mockJob } from "@/tests/fixtures";

export { mockArticle, mockJob };

const mockListResponse: ArticleListResponse = {
  count: 1,
  next: null,
  previous: null,
  results: [mockArticle],
};

export const handlers = [
  // GET /api/articles/
  http.get("/api/articles/", () => HttpResponse.json(mockListResponse)),

  // GET /api/articles/:id/
  http.get("/api/articles/:id/", ({ params }) => {
    if (params.id === "1") return HttpResponse.json(mockArticle);
    return HttpResponse.json({ detail: "Not found." }, { status: 404 });
  }),

  // POST /api/search/
  http.post("/api/search/", () =>
    HttpResponse.json({ ...mockJob, status: "pending", id: 2 }, { status: 202 })
  ),

  // GET /api/jobs/:id/
  http.get("/api/jobs/:id/", () => HttpResponse.json(mockJob)),

  // POST /api/articles/:id/analyze/
  http.post("/api/articles/:id/analyze/", () =>
    HttpResponse.json({ ...mockArticle, ai_processed: true }, { status: 202 })
  ),
];
