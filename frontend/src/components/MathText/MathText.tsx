/**
 * MathText — renderiza texto con notación LaTeX inline ($ ... $) usando KaTeX.
 *
 * Ejemplo de entrada (abstractos de arXiv):
 *   "La molécula $H_2O$ se disocia en $H^+$ y $OH^-$ bajo campo eléctrico"
 *
 * Fragmentos con $ se renderizan con KaTeX; el resto como texto plano.
 * Si KaTeX falla en un segmento, se muestra el texto original sin renderizar.
 */
import React from "react";
import { InlineMath } from "react-katex";
import "katex/dist/katex.min.css";

interface MathTextProps {
  text: string;
  className?: string;
}

/**
 * Divide el texto en segmentos de texto plano y segmentos math ($ ... $).
 * Maneja correctamente los delimitadores $$ como inline (KaTeX no tiene block
 * en react-katex@2, se renderiza inline de todas formas).
 */
function splitMath(text: string): Array<{ type: "text" | "math"; content: string }> {
  const segments: Array<{ type: "text" | "math"; content: string }> = [];
  // Captura $$...$$ primero (display), luego $...$  (inline)
  const pattern = /(\$\$[\s\S]+?\$\$|\$[^$\n]+?\$)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    // texto antes del match
    if (match.index > lastIndex) {
      segments.push({ type: "text", content: text.slice(lastIndex, match.index) });
    }
    // contenido math sin los delimitadores
    const raw = match[0];
    const inner = raw.startsWith("$$")
      ? raw.slice(2, -2)
      : raw.slice(1, -1);
    segments.push({ type: "math", content: inner.trim() });
    lastIndex = match.index + match[0].length;
  }

  // texto restante
  if (lastIndex < text.length) {
    segments.push({ type: "text", content: text.slice(lastIndex) });
  }

  return segments;
}

const MathSegment: React.FC<{ latex: string }> = ({ latex }) => {
  try {
    return <InlineMath math={latex} />;
  } catch {
    // Si KaTeX no puede parsear, mostramos el texto original
    return <span className="math-fallback">${latex}$</span>;
  }
};

const MathText: React.FC<MathTextProps> = ({ text, className }) => {
  if (!text) return null;

  // Si el texto no contiene $ no hace falta procesar
  if (!text.includes("$")) {
    return <span className={className}>{text}</span>;
  }

  const segments = splitMath(text);

  return (
    <span className={className}>
      {segments.map((seg, i) =>
        seg.type === "math" ? (
          <MathSegment key={i} latex={seg.content} />
        ) : (
          <React.Fragment key={i}>{seg.content}</React.Fragment>
        )
      )}
    </span>
  );
};

export default MathText;
