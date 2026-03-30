import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ArticleCard from "@/components/ArticleCard/ArticleCard";
import { mockArticle } from "@/tests/fixtures";

const renderWithRouter = (ui: React.ReactElement) =>
  render(<MemoryRouter>{ui}</MemoryRouter>);

describe("ArticleCard", () => {
  it("renders article title as a link", () => {
    renderWithRouter(<ArticleCard article={mockArticle} />);
    // El mock de i18n retorna el key, pero el título se muestra directamente
    expect(
      screen.getByRole("link", { name: /Water dissociation|Disociación/i })
    ).toBeInTheDocument();
  });

  it("shows source_db badge", () => {
    renderWithRouter(<ArticleCard article={mockArticle} />);
    expect(screen.getByText("ARXIV")).toBeInTheDocument();
  });

  it("shows DOI link when article has DOI", () => {
    renderWithRouter(<ArticleCard article={mockArticle} />);
    const doiLink = screen.getByText("DOI");
    expect(doiLink).toHaveAttribute("href", mockArticle.doi_url);
  });

  it("shows AI badge when article is processed", () => {
    renderWithRouter(<ArticleCard article={mockArticle} />);
    expect(document.querySelector(".article-card__ai-badge")).toBeInTheDocument();
  });

  it("does not show AI badge when not processed", () => {
    renderWithRouter(
      <ArticleCard article={{ ...mockArticle, ai_processed: false }} />
    );
    expect(document.querySelector(".article-card__ai-badge")).not.toBeInTheDocument();
  });

  it("shows year", () => {
    renderWithRouter(<ArticleCard article={mockArticle} />);
    expect(screen.getByText("2023")).toBeInTheDocument();
  });
});
