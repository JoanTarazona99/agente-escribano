import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export default function NotFound() {
  const { t } = useTranslation();

  return (
    <div style={{ textAlign: "center", padding: "4rem 1rem" }}>
      <h1 style={{ fontSize: "4rem", marginBottom: "0.5rem" }}>404</h1>
      <p style={{ color: "#a1a1aa", fontSize: "1rem" }}>{t("common.not_found")}</p>
      <Link
        to="/"
        style={{
          display: "inline-block",
          marginTop: "1.5rem",
          padding: "0.5rem 1.5rem",
          border: "1px solid #2e2e33",
          borderRadius: "6px",
          textDecoration: "none",
          color: "inherit",
        }}
      >
        ← {t("common.back")}
      </Link>
    </div>
  );
}
