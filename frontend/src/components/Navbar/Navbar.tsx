import React from "react";
import { Link, NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import LanguageSwitcher from "@/components/LanguageSwitcher/LanguageSwitcher";
import { NotebookButton } from "@/components/NotebookButton/NotebookButton";
import "./Navbar.css";

export default function Navbar() {
  const { t } = useTranslation();

  return (
    <header className="navbar">
      <div className="navbar__inner">
        <Link to="/" className="navbar__brand">
          <span className="navbar__brand-icon">🔬</span>
          <span className="navbar__brand-text">Agente Escribano</span>
        </Link>

        <nav className="navbar__nav">
          <NotebookButton />
          <NavLink to="/settings" className={({ isActive }) => `navbar__link${isActive ? " navbar__link--active" : ""}`}>
            {t("nav.settings")}
          </NavLink>
        </nav>

        <LanguageSwitcher />
      </div>
    </header>
  );
}
