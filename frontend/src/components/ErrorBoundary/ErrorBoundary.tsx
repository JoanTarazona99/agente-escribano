import React from "react";

interface Props {
  children: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: "2rem", textAlign: "center" }}>
          <h1>⚠️ Algo salió mal</h1>
          <p style={{ color: "#a1a1aa", marginTop: "0.5rem" }}>
            {this.state.error?.message ?? "Error desconocido"}
          </p>
          <button
            style={{
              marginTop: "1rem",
              padding: "0.5rem 1.5rem",
              border: "1px solid #2e2e33",
              borderRadius: "6px",
              cursor: "pointer",
              background: "#1e1e22",
              color: "#e4e4e7",
            }}
            onClick={() => {
              this.setState({ hasError: false, error: null });
              window.location.href = "/";
            }}
          >
            Volver al inicio
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
