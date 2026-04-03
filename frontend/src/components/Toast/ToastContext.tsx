import {
  createContext,
  useContext,
  useCallback,
  useState,
  type ReactNode,
} from "react";
import ToastContainer, { type ToastItem, type ToastType } from "./Toast";

interface ToastContextValue {
  success: (message: string, duration?: number) => string;
  error: (message: string, duration?: number) => string;
  info: (message: string, duration?: number) => string;
  loading: (message: string) => string;
  dismiss: (id: string) => void;
  update: (id: string, message: string, type?: ToastType, duration?: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let toastCounter = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback(
    (message: string, type: ToastType, duration?: number): string => {
      const id = `toast-${++toastCounter}`;
      const item: ToastItem = {
        id,
        message,
        type,
        duration: duration ?? (type === "loading" ? undefined : 5000),
      };
      setToasts((prev) => [...prev.slice(-4), item]); // max 5 visible
      return id;
    },
    [],
  );

  const updateToast = useCallback(
    (id: string, message: string, type?: ToastType, duration?: number) => {
      setToasts((prev) =>
        prev.map((t) =>
          t.id === id
            ? {
                ...t,
                message,
                type: type ?? t.type,
                duration: duration ?? (type === "loading" ? undefined : 5000),
              }
            : t,
        ),
      );
    },
    [],
  );

  const ctx: ToastContextValue = {
    success: useCallback(
      (msg: string, dur?: number) => addToast(msg, "success", dur),
      [addToast],
    ),
    error: useCallback(
      (msg: string, dur?: number) => addToast(msg, "error", dur ?? 8000),
      [addToast],
    ),
    info: useCallback(
      (msg: string, dur?: number) => addToast(msg, "info", dur),
      [addToast],
    ),
    loading: useCallback(
      (msg: string) => addToast(msg, "loading"),
      [addToast],
    ),
    dismiss: removeToast,
    update: updateToast,
  };

  return (
    <ToastContext.Provider value={ctx}>
      {children}
      <ToastContainer toasts={toasts} onClose={removeToast} />
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a <ToastProvider>");
  }
  return ctx;
}
