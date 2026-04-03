import { BrowserRouter, Route, Routes } from "react-router-dom";
import ErrorBoundary from "@/components/ErrorBoundary/ErrorBoundary";
import { ToastProvider } from "@/components/Toast/ToastContext";
import Navbar from "@/components/Navbar/Navbar";
import Home from "@/pages/Home";
import Settings from "@/pages/Settings";
import Notebook from "@/pages/Notebook";
import NotFound from "@/pages/NotFound";
import "./App.css";

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
        <ToastProvider>
          <div className="app">
            <Navbar />
            <main className="app__main">
              <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/notebooks/:id" element={<Notebook />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </main>
          </div>
        </ToastProvider>
      </ErrorBoundary>
    </BrowserRouter>
  );
}
