import "@testing-library/jest-dom";

// Mock compartido de changeLanguage, accesible desde tests
export const mockChangeLanguage = jest.fn();

// Mock de i18next para tests de componentes
jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      changeLanguage: mockChangeLanguage,
      language: "es",
    },
  }),
  Trans: ({ children }: { children: React.ReactNode }) => children,
  initReactI18next: { type: "3rdParty", init: jest.fn() },
}));
