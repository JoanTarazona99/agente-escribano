import { useTranslation } from "react-i18next";
import type { SearchJob } from "@/types";
import "./ProgressIndicator.css";

interface ProgressIndicatorProps {
  job: SearchJob;
}

const STATUS_ICONS: Record<string, string> = {
  pending: "⏳",
  running: "🔄",
  completed: "✅",
  failed: "❌",
};

export default function ProgressIndicator({ job }: ProgressIndicatorProps) {
  const { t } = useTranslation();

  return (
    <div className={`progress-indicator progress-indicator--${job.status}`} role="status">
      <span className="progress-indicator__icon">{STATUS_ICONS[job.status] ?? "⏳"}</span>
      <div className="progress-indicator__body">
        <p className="progress-indicator__status">
          {t(`job.status.${job.status}`)}
        </p>
        {job.status === "completed" && (
          <p className="progress-indicator__detail">
            {t("job.completed_detail", {
              found: job.total_found,
              saved: job.total_saved,
            })}
          </p>
        )}
        {job.status === "failed" && job.error_message && (
          <p className="progress-indicator__error">{job.error_message}</p>
        )}
        {job.status === "running" && (
          <div className="progress-indicator__bar" aria-hidden="true">
            <div className="progress-indicator__bar-fill" />
          </div>
        )}
      </div>
    </div>
  );
}
