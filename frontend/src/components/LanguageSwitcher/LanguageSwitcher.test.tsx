import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { useTranslation } from "react-i18next";
import LanguageSwitcher from "@/components/LanguageSwitcher/LanguageSwitcher";

// El mock de react-i18next ya está en jest.setup.ts
describe("LanguageSwitcher", () => {
  it("renders ES, RU and EN buttons", () => {
    render(<LanguageSwitcher />);
    expect(screen.getByText("ES")).toBeInTheDocument();
    expect(screen.getByText("RU")).toBeInTheDocument();
    expect(screen.getByText("EN")).toBeInTheDocument();
  });

  it("marks current language button as active (aria-pressed)", () => {
    render(<LanguageSwitcher />);
    // El mock de i18n.language es "es"
    const esBtn = screen.getByRole("button", { name: "ES" });
    expect(esBtn).toHaveAttribute("aria-pressed", "true");
    const enBtn = screen.getByRole("button", { name: "EN" });
    expect(enBtn).toHaveAttribute("aria-pressed", "false");
  });

  it("calls changeLanguage when a button is clicked", () => {
    // Obtenemos la función mock directamente del módulo mockeado
    const { i18n } = useTranslation();
    render(<LanguageSwitcher />);
    fireEvent.click(screen.getByText("RU"));
    expect(i18n.changeLanguage).toHaveBeenCalledWith("ru");
  });
});

