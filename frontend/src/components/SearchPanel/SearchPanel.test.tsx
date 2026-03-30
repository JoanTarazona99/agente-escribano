import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { useTranslation } from "react-i18next";
import SearchPanel from "@/components/SearchPanel/SearchPanel";

const mockOnSearch = jest.fn();

describe("SearchPanel", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders title and submit button", () => {
    render(<SearchPanel onSearch={mockOnSearch} />);
    expect(screen.getByText("search.title")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "search.submit" })).toBeInTheDocument();
  });

  it("calls onSearch when form is submitted", () => {
    render(<SearchPanel onSearch={mockOnSearch} />);
    const button = screen.getByRole("button", { name: "search.submit" });
    fireEvent.click(button);
    expect(mockOnSearch).toHaveBeenCalledTimes(1);
  });

  it("disables submit button when isLoading is true", () => {
    render(<SearchPanel onSearch={mockOnSearch} isLoading={true} />);
    const button = screen.getByRole("button", { name: "search.searching" });
    expect(button).toBeDisabled();
  });

  it("shows all 4 source checkboxes", () => {
    render(<SearchPanel onSearch={mockOnSearch} />);
    const sources = ["arxiv", "elibrary", "scopus", "wos"];
    sources.forEach((src) => {
      expect(screen.getByText(src.toUpperCase())).toBeInTheDocument();
    });
  });

  it("passes selected sources to onSearch", () => {
    render(<SearchPanel onSearch={mockOnSearch} />);
    // Por defecto arxiv y elibrary están seleccionados
    fireEvent.click(screen.getByRole("button", { name: "search.submit" }));
    const [, sources] = mockOnSearch.mock.calls[0];
    expect(sources).toContain("arxiv");
    expect(sources).toContain("elibrary");
  });
});
