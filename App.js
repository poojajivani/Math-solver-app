import React, { useState } from "react";
import axios from "axios";
import "./App.css";
import "katex/dist/katex.min.css";
import { BlockMath } from "react-katex";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

const API_URL = "http://127.0.0.1:8000/chat";

// --- UTILITY FUNCTIONS ---

function looksLikeLatex(value = "") {
  return /\\[a-zA-Z]+|[_^{}=+\-*/()]|\\frac|\\sqrt/.test(value);
}

function normalizeMath(value = "") {
  return String(value || "")
    .replace(/^```latex/i, "")
    .replace(/^```tex/i, "")
    .replace(/^```/i, "")
    .replace(/```$/i, "")
    // Remove $...$
    .replace(/^\$\$/, "")
    .replace(/\$\$$/, "")
    .replace(/^\$/, "")
    .replace(/\$$/, "")
    .replace(/\$/g, "")
    // Remove \( \) and \[ \]
    .replace(/^\\\(/, "")
    .replace(/\\\)$/, "")
    .replace(/^\\\[/, "")
    .replace(/\\\]$/, "")
    .trim();
}

function cleanDisplayValue(value = "") {
  return String(value)
    .split(/\b(?:Visualization|Visualisation|Graph|Simplified form|Alternative form|Suggestions?|Step\s+\d+)\b/i)[0]
    .trim()
    .replace(/[:;,-]\s*$/g, "");
}

function repairLatex(value = "") {
  return String(value)
    .replace(/\\rightight/g, "\\right")
    .replace(/\\leftleft/g, "\\left")
    .replace(/\bheta\b/g, "\\theta")
    .replace(/\ban(?=\s*(?:\^|\(|\\left|\{))/g, "\\tan")
    .replace(/\bsec(?=\s*(?:\^|\(|\\left|\{))/g, "\\sec")
    .replace(/(^|[^\\])\bright\b/g, "$1\\right")
    .replace(/\bight(?=\s*\))/g, "\\right")
    .replace(/(^|[^\\])\bleft\b/g, "$1\\left")
    .replace(/(^|[^\\])\bfrac\b/g, "$1\\frac")
    .replace(/(^|[^\\])\bpi\b/g, "$1\\pi")
    .replace(/(^|[^\\])\btheta\b/g, "\\theta")
    .replace(/(^|[^\\])\b(sin|cos|tan|sec|csc|cot|ln|log)\b/g, "$1\\$2")
    .replace(/(\d+)\s*\/\s*(\d+)/g, "\\frac{$1}{$2}")
    .replace(/\\right\s*\)/g, "\\right)");
}

// --- SUB COMPONENTS ---

function MathText({ text }) {
  if (!text) return null;

  const content = String(text)
    .replace(/\\\(/g, "$")
    .replace(/\\\)/g, "$")
    .replace(/\\\[/g, "$$")
    .replace(/\\\]/g, "$$");

  return (
    <ReactMarkdown
      remarkPlugins={[remarkMath]}
      rehypePlugins={[rehypeKatex]}
    >
      {content}
    </ReactMarkdown>
  );
}

function DisplayMath({ value, boxed = false }) {
  if (!value) return null;

  const math = repairLatex(
    normalizeMath(
      cleanDisplayValue(value).replace(/\$/g, "")
    )
  );
  const className = boxed ? "display-math boxed-answer" : "display-math";

  if (!looksLikeLatex(math)) {
    return <div className={className}>{math}</div>;
  }

  return (
    <div className={className}>
      <BlockMath
        math={math}
        renderError={() => <code>{math}</code>}
      />
    </div>
  );
}

function RenderBlock({ block }) {
  if (!block) return null;

  switch (block.type) {
    case "text":
      return (
        <div className="explanation-block">
          {block.content}
        </div>
      );
    case "equation":
      return (
        <div className="equation-block">
          <BlockMath math={block.content} />
        </div>
      );
    case "answer":
      return (
        <div className="answer-block">
          <BlockMath math={block.content} />
        </div>
      );
    default:
      return null;
  }
}

// --- MAIN APP COMPONENT ---

function App() {
  const [question, setQuestion] = useState("");
  const [images, setImages] = useState([]);
  const [previews, setPreviews] = useState([]);
  const [solution, setSolution] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showImage, setShowImage] = useState(false);
  const [preview, setPreview] = useState(null);

  const sendMessage = async () => {
    if (!question.trim() && images.length === 0) {
      alert("Enter question or upload image");
      return;
    }

    try {
      setLoading(true);

      const formData = new FormData();
      formData.append("question", question);
      images.forEach((image) => formData.append("files", image));

      const response = await axios.post(
        API_URL,
        formData
      );

      setSolution(response.data);
    } catch (error) {
      console.error(error);
      alert(error.response ? JSON.stringify(error.response.data) : "Backend not running");
    } 
    finally {
      setLoading(false);
    }
  };

  const handleImageUpload = (event) => {
    const selectedFiles = Array.from(event.target.files);

    if (selectedFiles.length > 0) {
      setImages((previous) => [...previous, ...selectedFiles]);
      setPreviews((previous) => [
        ...previous,
        ...selectedFiles.map((file) => URL.createObjectURL(file)),
      ]);
    }

    event.target.value = null;
  };

  const removeImage = (index) => {
    setImages((previous) => previous.filter((_, itemIndex) => itemIndex !== index));
    setPreviews((previous) => previous.filter((_, itemIndex) => itemIndex !== index));
  };

  return (
    <main className="app-shell">
      <section className="composer">
        <div className="brand-row">
          <div>
            <h1>AI Math Solver</h1>
            <h3>Step-by-step answers with clean math rendering</h3>
          </div>
        </div>

        <div className="input-row">
          <input
            type="text"
            placeholder="Ask a math question, or upload an image..."
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") sendMessage();
            }}
          />
          <button onClick={sendMessage} disabled={loading}>
            {loading ? "Solving" : "Send"}
          </button>
        </div>

        <label className="upload-box">
          <input
            type="file"
            accept="image/*"
            multiple
            hidden
            onChange={handleImageUpload}
          />

          {previews.length > 0 ? (
            <div className="multi-preview-grid">
              {previews.map((imagePreview, index) => (
                <div key={imagePreview} className="preview-card">
                  <button
                    className="remove-image-btn"
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      removeImage(index);
                    }}
                    aria-label="Remove image"
                  >
                    ×
                  </button>
                  <img
                    src={imagePreview}
                    alt="Uploaded preview"
                    className="inside-preview-image"
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      setPreview(imagePreview);
                      setShowImage(true);
                    }}
                  />
                </div>
              ))}
            </div>
          ) : (
            <div className="upload-content">
              <strong>Upload image</strong>
              <span>Multiple images supported</span>
            </div>
          )}
        </label>
      </section>

      {showImage && (
        <div className="fullscreen-overlay" onClick={() => setShowImage(false)}>
          <button className="close-button" onClick={() => setShowImage(false)}>
            ×
          </button>
          <img
            src={preview}
            alt="Full preview"
            className="fullscreen-image"
            onClick={(event) => event.stopPropagation()}
          />
        </div>
      )}

      {loading && <div className="loading">Solving...</div>}

      {solution && (
        <section className="solution-paper">
        <div className="problem-line">
          <strong>Problem:</strong>
          <span>{solution.question || question || "Image question"}</span>
        </div>

        {solution.steps?.map((step, index) => (
          <section key={`${step.title}-${index}`} className="solution-step">
            <h2>
              Step {index + 1}: {String(step.title)
                .replace(/\$/g, "")
                .replace(/\\[a-zA-Z]+/g, "")
                .trim()}
            </h2>

            {step.explanation && (
              <div className="step-explanation">
                <ReactMarkdown
                  remarkPlugins={[remarkMath]}
                  rehypePlugins={[rehypeKatex]}
                >
                  {step.explanation}
                </ReactMarkdown>
              </div>
            )}

            {step.expression && (
              <DisplayMath value={step.expression} />
            )}

            {step.result && (
              <DisplayMath value={step.result} />
            )}
          </section>
        ))}

        <section className="answer-section">
          <h2>Answer</h2>
          <DisplayMath value={solution.answer} boxed />
        </section>

          {solution.suggestions?.length > 0 && (
            <section className="suggestions-section">
              <h2>Suggestions</h2>
              <ul>
                {solution.suggestions.map((item, index) => (
                  <li key={`${item}-${index}`}>
                    <MathText text={item} />
                  </li>
                ))}
              </ul>
            </section>
          )}
        </section>
      )}
    </main>
  );
}

export default App;