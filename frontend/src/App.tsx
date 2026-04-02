import { BrowserRouter, Route, Routes } from "react-router-dom";
import ErrorBoundary from "@/components/ErrorBoundary/ErrorBoundary";
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
      </ErrorBoundary>
    </BrowserRouter>
  );
}
