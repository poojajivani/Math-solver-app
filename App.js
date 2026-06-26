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

// eslint-disable-next-line no-unused-vars
function looksLikeLatex(value = "") {
  return (
    value.includes("\\") ||
    value.includes("^") ||
    value.includes("∫") ||
    value.includes("Σ") ||
    value.includes("√")
  );
}


function normalizeMath(value = "") {
  return String(value || "")
    .replace(/\\\\frac/g, "\\frac")
    .replace(/\\\\sqrt/g, "\\sqrt")
    .replace(/\\\\sum/g, "\\sum")
    .replace(/\\\\int/g, "\\int")
    .replace(/^```latex/i, "")
    .replace(/^```tex/i, "")
    .replace(/^```/i, "")
    .replace(/```$/i, "")
    .replace(/\$/g, "")
    .replace(/\\cdot/g, "\\times")
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
    .replace(/(\d+)pi/g, "$1\\\\pi")
    .replace(/\bpi\b/g, "\\pi")
    .replace(/\ban(?=\s*(?:\^|\(|\\left|\{))/g, "\\tan")
    .replace(/\bsec(?=\s*(?:\^|\(|\\left|\{))/g, "\\sec")
    .replace(/(^|[^\\])\bright\b/g, "$1\\right")
    .replace(/\bight(?=\s*\))/g, "\\right")
    .replace(/(^|[^\\])\bleft\b/g, "$1\\left")
    .replace(/\\\\frac/g, "\\frac")
    .replace(/(\d+)\((\d+)\)/g, "$1\\times $2")
    .replace(/(\w+)\^(\d+)/g, "$1^{$2}")
    .replace(/\\\\sqrt/g, "\\sqrt")
    .replace(/\\\\sum/g, "\\sum")
    .replace(/\\\\int/g, "\\int")
    .replace(/\*/g, "\\times ")
    .replace(/^\$/, "")
    .replace(/\$$/, "")
    .replace(/(^|[^\\])\bpi\b/g, "$1\\pi")
    .replace(/(^|[^\\])\btheta\b/g, "\\theta")
    .replace(/(^|[^\\])\b(sin|cos|tan|sec|csc|cot|ln|log)\b/g, "$1\\$2")
    .replace(/(\d+)\s*\/\s*(\d+)/g, "\\frac{$1}{$2}")
    .replace(/\\right\s*\)/g, "\\right)")
    .replace(/\bpi\b/g, "\\pi")
    .replace(/\bsin\b/g, "\\sin")
    .replace(/\bcos\b/g, "\\cos")
    .replace(/\btan\b/g, "\\tan")
}

// --- SUB COMPONENTS ---

function MathText({ text }) {
  if (!text) return null;

  let content = String(text)
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

function restoreQuestionSpacing(value = "") {
  return String(value)
    .replace(/Giventhematrices/gi, "Given the matrices ")
    .replace(/shownbelow/gi, " shown below")
    .replace(/find([A-Z])/g, "find $1")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\bAandB\b/g, "A and B")
    .replace(/\b([A-Z])and\s+([A-Z])\b/g, "$1 and $2")
    .replace(/\b([A-Z])and([A-Z])\b/g, "$1 and $2")
    .replace(/([,.!?;:])([A-Za-z])/g, "$1 $2")
    .replace(/\s*-\s*/g, " - ")
    .replace(/\s+/g, " ")
    .trim();
}

function formatQuestionText(value = "") {
  const text = restoreQuestionSpacing(value);

  if (/[$]|\\\(|\\\[/.test(text)) {
    return text;
  }

  return text.replace(
    /([A-Za-z0-9().+\-*/^\\]+(?:\s*[=+\-*/^]\s*[A-Za-z0-9().+\-*/^\\]+)+)/g,
    (match) => `$${repairLatex(normalizeMath(match))}$`
  );
}

function ProblemQuestion({ value }) {
  if (!value) return null;

  return (
    <div className="problem-question">
      <MathText text={formatQuestionText(value)} />
    </div>
  );
}

function DisplayMath({ value, boxed = false }) {
  if (!value) return null;

  const math = repairLatex(
    normalizeMath(
      cleanDisplayValue(value)
    )
  );

  const className = boxed
    ? "display-math boxed-answer"
    : "display-math";

  return (
    <div className={className}>
      <BlockMath
        math={math}
        renderError={() => (
          <div>{value}</div>
        )}
      />
    </div>
  );
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
      
      console.log("Sending request...");
      const response = await axios.post(
        API_URL,
        formData,
        {
          headers: {
            "Content-Type": "multipart/form-data",
          },
        }
      );
      console.log("Response:", response.data);
      console.log(response.data);

      if (response.data.error) {
        alert(response.data.error);
        return;
      }
      setSolution(response.data);
    } 
    catch (error) {
      console.error("FULL ERROR:", error);

      if (error.response) {
        console.log("RESPONSE:", error.response.data);
        alert(JSON.stringify(error.response.data));
      } else if (error.request) {
        alert("Request reached server but no valid response");
      } else {
        alert(error.message);
      }
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

      {solution.problems
        ?.filter(
          (problem) =>
            problem.question !== "No image provided" &&
            problem.answer !== "No image provided"
        )
        .map((problem, problemIndex) => (
        <div key={problemIndex}>

          {problem.source === "text" && (
            <h1>Text Problem</h1>
          )}

          {problem.source === "image" && (
            <h1>Image Problem</h1>
          )}
         <ProblemQuestion value={problem.question} />

              {Array.isArray(problem.steps) &&
            problem.steps.map((step, index) => (
            <section key={index}>
              <h2>
                Step {index + 1}: {step.title}
              </h2>

              <div className="step-explanation">
                <MathText text={step.explanation} />
              </div>

              {step.expression && (
                <BlockMath
                  math={repairLatex(
                    normalizeMath(step.expression)
                  )}
                  renderError={() => (
                    <div>{step.expression}</div>
                  )}
                />
              )}

              {step.result &&
              step.result.trim() !== "" &&
              step.result !== step.expression && (
                  <DisplayMath value={step.result} />
              )}
            </section>
          ))}

          <h2>Answer</h2>

          <DisplayMath
            value={problem.answer}
            boxed
          />

          <hr />
        </div>
      ))}

    </section>
  )}
    </main>
  );
}
export default App;
