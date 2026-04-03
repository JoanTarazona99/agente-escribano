import { useState, useEffect } from "react";
import "./Toast.css";

export type ToastType = "success" | "error" | "info" | "loading";

export interface ToastItem {
  id: string;
  message: string;
  type: ToastType;
  duration?: number;
}

interface ToastProps {
  item: ToastItem;
  onClose: (id: string) => void;
}

const ICONS: Record<ToastType, React.ReactNode> = {
  success: "✅",
  error: "❌",
  info: "ℹ️",
  loading: <span className="toast__spinner" />,
};

function Toast({ item, onClose }: ToastProps) {
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    if (item.type === "loading" || !item.duration) return;

    const timer = setTimeout(() => {
      setExiting(true);
      setTimeout(() => onClose(item.id), 300);
    }, item.duration);

    return () => clearTimeout(timer);
  }, [item.id, item.duration, item.type, onClose]);

  const handleClose = () => {
    setExiting(true);
    setTimeout(() => onClose(item.id), 300);
  };

  return (
    <div
      className={`toast toast--${item.type}${exiting ? " toast--exiting" : ""}`}
      role="alert"
    >
      <span className="toast__icon">{ICONS[item.type]}</span>
      <span className="toast__message">{item.message}</span>
      <button className="toast__close" onClick={handleClose} aria-label="Close">
        ×
      </button>
    </div>
  );
}

interface ToastContainerProps {
  toasts: ToastItem[];
  onClose: (id: string) => void;
}

export default function ToastContainer({ toasts, onClose }: ToastContainerProps) {
  if (toasts.length === 0) return null;

  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <Toast key={t.id} item={t} onClose={onClose} />
      ))}
    </div>
  );
}
