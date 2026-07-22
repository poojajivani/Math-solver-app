import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import "./App.css";
import { isSupabaseConfigured, supabase } from "./supabase";

import "katex/dist/katex.min.css";
import { BlockMath } from "react-katex";

import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

import {
  FiSend,
  FiImage,
  FiTrash2,
  FiMaximize2
} from "react-icons/fi";

function getApiUrl() {
  const configuredUrl = process.env.REACT_APP_API_URL?.trim();

  if (configuredUrl) {
    const normalizedUrl = configuredUrl.replace(/\/+$/, "");
    return normalizedUrl.endsWith("/chat")
      ? normalizedUrl
      : `${normalizedUrl}/chat`;
  }

  // Works on localhost and when the frontend is opened from another device
  // on the same network. The FastAPI server listens on port 8000.
  const host = window.location.hostname || "127.0.0.1";

  // If the resolved hostname looks like an unreachable local network IP
  // (e.g. an old DHCP address), prefer loopback so local dev works.
  const fallbackHost = /^192\.168\.|^10\.|^172\.(1[6-9]|2[0-9]|3[0-1])\./.test(host)
    ? "127.0.0.1"
    : host;

  const url = `http://${fallbackHost}:8000/chat`;
  console.info("API URL resolved to", url);
  return url;
}

const API_URL = getApiUrl();
const KATEX_OPTIONS = {
  throwOnError: false,
  strict: false,
  trust: false
};
const MARKDOWN_REMARK_PLUGINS = [remarkMath];
const MARKDOWN_REHYPE_PLUGINS = [[rehypeKatex, KATEX_OPTIONS]];

/* ----------------------------
   LATEX HELPERS
-----------------------------*/

function normalizeMath(value = "") {
  return String(value)
    .replace(/\\\\frac/g, "\\frac")
    .replace(/\\\\sqrt/g, "\\sqrt")
    .replace(/\\\\sum/g, "\\sum")
    .replace(/\\\\int/g, "\\int")
    .replace(/\$/g, "")
    .trim();
}

function repairLatex(value = "") {
  const repaired = String(value)
    .replace(/\\rightight/g, "\\right")
    .replace(/\\leftleft/g, "\\left")
    .replace(/\\\\frac/g, "\\frac")
    .replace(/\\\\sqrt/g, "\\sqrt")
    .replace(/\\\\sum/g, "\\sum")
    .replace(/\\\\int/g, "\\int")
    .replace(/(^|[^\\])\btanpi(?=[A-Za-z0-9])/g, "$1\\tan\\pi")
    .replace(/(^|[^\\])\bcospi(?=[A-Za-z0-9])/g, "$1\\cos\\pi")
    .replace(/(^|[^\\])\bsinpi(?=[A-Za-z0-9])/g, "$1\\sin\\pi")
    .replace(/(^|[^\\])\b(pi|sin|cos|tan|sec|csc|cot|log|ln|theta|alpha|beta|gamma|int|sum|lim|sqrt|frac)\b/g, "$1\\$2")
    .replace(/\\pi([A-Za-z])/g, "\\pi $1")
    .replace(/\\sin([A-Za-z])/g, "\\sin $1")
    .replace(/\\cos([A-Za-z])/g, "\\cos $1")
    .replace(/\\tan([A-Za-z])/g, "\\tan $1")
    .replace(/\\sec([A-Za-z])/g, "\\sec $1")
    .replace(/\\csc([A-Za-z])/g, "\\csc $1")
    .replace(/\\cot([A-Za-z])/g, "\\cot $1");

  // AI JSON occasionally leaves matrix row breaks as one backslash. KaTeX
  // requires two, so repair only standalone slashes inside matrix bodies.
  return repaired.replace(
    /\\begin\{([a-zA-Z*]+)\}([\s\S]*?)\\end\{\1\}/g,
    (matrix) => matrix.replace(/(^|[^\\])\\(?![\\a-zA-Z])/g, "$1\\\\")
  );
}

function wrapBareLatex(value = "") {
  const text = String(value);
  let output = "";
  let insideMath = false;
  let index = 0;

  while (index < text.length) {
    const char = text[index];

    if (char === "$") {
      output += char;
      if (text[index + 1] === "$") {
        output += "$";
        index += 2;
      } else {
        index += 1;
      }
      insideMath = !insideMath;
      continue;
    }

    if (insideMath) {
      output += char;
      index += 1;
      continue;
    }

    if (char === "\\") {
      const expr = parseLatexExpression(text, index);

      if (expr) {
        output += `$${expr}$`;
        index += expr.length;
        continue;
      }
    }

    output += char;
    index += 1;
  }

  return output;
}

function parseLatexExpression(text, start) {
  if (text[start] !== "\\") return null;

  let index = start + 1;
  const commandMatch = text.slice(index).match(/^[a-zA-Z]+/);

  if (!commandMatch) return null;

  let expr = "\\" + commandMatch[0];
  index += commandMatch[0].length;

  while (index < text.length) {
    const nextChar = text[index];

    if (nextChar === "{") {
      const balanced = readBalanced(text, index, "{", "}");
      if (!balanced) break;
      expr += balanced.content;
      index = balanced.next;
      continue;
    }

    // A LaTeX command commonly has a subscript/superscript immediately
    // after it, e.g. \sum_{n=1}^{N}. Keep those groups in the same math
    // fragment instead of leaving raw _{...}^{...} in prose.
    if (nextChar === "_" || nextChar === "^") {
      expr += nextChar;
      index += 1;

      if (text[index] === "{") {
        const balanced = readBalanced(text, index, "{", "}");
        if (!balanced) break;
        expr += balanced.content;
        index = balanced.next;
      } else if (index < text.length && /^[A-Za-z0-9]$/.test(text[index])) {
        expr += text[index];
        index += 1;
      }
      continue;
    }

    if (nextChar === "(") {
      const balanced = readBalanced(text, index, "(", ")");
      if (!balanced) break;
      expr += balanced.content;
      index = balanced.next;
      continue;
    }

    if (nextChar === "\\") {
      const nested = parseLatexExpression(text, index);
      if (!nested) break;
      expr += nested;
      index += nested.length;
      continue;
    }

    if (/^[)\]}]$/.test(nextChar) && /\\right$/.test(expr)) {
      expr += nextChar;
      index += 1;
      continue;
    }

    if (/^[A-Za-z0-9]$/.test(nextChar)) {
      expr += nextChar;
      index += 1;
      continue;
    }

    break;
  }

  return expr;
}

function readBalanced(text, start, openChar, closeChar) {
  if (text[start] !== openChar) return null;

  let depth = 0;
  let index = start;
  let content = "";

  while (index < text.length) {
    const char = text[index];
    content += char;

    if (char === openChar) {
      depth += 1;
    } else if (char === closeChar) {
      depth -= 1;
      if (depth === 0) {
        return { content, next: index + 1 };
      }
    }

    index += 1;
  }

  return null;
}

function isEmptyAnswer(value) {
  const text = String(value ?? "").trim();
  return !text || /^(none|null|undefined|nan)$/i.test(text);
}

function isMathLike(value) {
  const text = String(value ?? "").trim();

  if (isEmptyAnswer(text)) return false;

  return (
    /\\(frac|sqrt|sin|cos|tan|log|ln|theta|alpha|beta|gamma|pi|int|sum|lim|left|right|cdot|times|begin|end)/.test(text) ||
    /[\^_{}]/.test(text) ||
    /[=+\-*/]/.test(text) ||
    /\b[a-zA-Z]\b/.test(text)
  );
}

function isStandaloneMath(value) {
  const text = String(value ?? "").trim();
  if (!isMathLike(text)) return false;

  const proseWords = text
    .replace(/\\[a-zA-Z]+/g, " ")
    .match(/[a-zA-Z]{2,}/g) || [];
  const mathWords = new Set(["sin", "cos", "tan", "log", "ln", "lim", "pi"]);

  return proseWords.every((word) => mathWords.has(word.toLowerCase()));
}

function MathText({ text }) {
  if (!text) return null;

  const repairedText = repairLatex(String(text));

  return (
    <ReactMarkdown
      remarkPlugins={MARKDOWN_REMARK_PLUGINS}
      rehypePlugins={MARKDOWN_REHYPE_PLUGINS}
    >
      {wrapBareLatex(repairedText)}
    </ReactMarkdown>
  );
}

function DisplayMath({ value }) {
  if (isEmptyAnswer(value)) return null;

  return (
    <BlockMath
      // For display math, pass raw LaTeX (no $ wrappers) and remove
      // `\newline` which KaTeX warns about in display mode.
      math={repairLatex(
        normalizeMath(String(value)).replace(/\\newline/g, " ")
      )}
      renderError={() => <div className="math-fallback">{String(value)}</div>}
    />
  );
}

function StepValue({ value }) {
  if (isEmptyAnswer(value)) return null;

  // Vision models occasionally return a label (for example, "Calculated
  // values") in a step field. Rendering prose through KaTeX removes spaces
  // and makes it look like malformed math.
  return isMathLike(value)
    ? <DisplayMath value={value} />
    : <span className="math-fallback">{String(value)}</span>;
}

function AnswerValue({ value }) {
  if (isEmptyAnswer(value)) {
    return <span>No answer found</span>;
  }

  return isMathLike(value)
    ? <DisplayMath value={value} />
    : <span>{String(value)}</span>;
}

export function QuestionText({ question }) {
  if (!question) return null;

  const text = String(question).trim();

  /*
   * A question is prose, even when it contains variables or operators.
   * Rendering the whole sentence as one KaTeX expression makes TeX treat
   * spaces as insignificant ("Given the matrices" -> "Giventhematrices").
   * MathText preserves prose and renders only delimited/bare LaTeX fragments.
   */
  return isStandaloneMath(text)
    ? <DisplayMath value={text} />
    : <MathText text={text} />;
}

export default function App() {

  /* ----------------------------
      STATES
  -----------------------------*/

  const [question, setQuestion] = useState("");

  const [images, setImages] = useState([]);

  const [previews, setPreviews] = useState([]);

  const [solution, setSolution] = useState(null);

  const [loading, setLoading] = useState(false);

  const [dragActive, setDragActive] = useState(false);

  const [fullscreenImage, setFullscreenImage] = useState(null);

  const textareaRef = useRef(null);

  const getAnswerSummary = (solutionData) => {
    if (!solutionData?.problems?.length) return "";

    return solutionData.problems
      .map((problem) => problem.answer || "")
      .filter(Boolean)
      .join(" \n\n");
  };

  const saveHistoryItem = async (questionText, solutionData) => {
    if (!isSupabaseConfigured) return;
    if (!questionText && !solutionData?.problems?.length) return;

    const {
      data: { session: currentSession },
      error: sessionError,
    } = await supabase.auth.getSession();

    if (sessionError) {
      console.error("Failed to refresh Supabase session before saving:", sessionError.message);
      return;
    }

    if (!currentSession?.user?.id) {
      console.error("No Supabase user session available for saving history.");
      return;
    }

    let imageUrl = null;

    if (images.length > 0) {
      const file = images[0];

      const fileName = `${currentSession.user.id}/${Date.now()}-${file.name}`;

      const { data: uploadData, error: uploadError } =
        await supabase.storage
          .from("math-images")
          .upload(fileName, file);

      if (uploadError) {
        console.error("Storage upload failed:", uploadError);
      } else {
        console.log("Storage upload success:", uploadData);

        const { data } = supabase.storage
          .from("math-images")
          .getPublicUrl(fileName);

        imageUrl = data.publicUrl;
      }
    }

    const defaultQuestion =
      solutionData.problems?.[0]?.question ||
      solutionData.problems?.[0]?.answer ||
      solutionData.problems?.[0]?.steps?.[0]?.expression ||
      "Image problem";

    const record = {
      user_id: currentSession.user.id,
      question: questionText || defaultQuestion,
      answer: getAnswerSummary(solutionData),
      solution: solutionData,
      image_url: imageUrl
    };

    console.log("Current session:", currentSession);
    console.log("User ID:", currentSession?.user?.id);
    console.log("Record being inserted:", record);

    const { error } = await supabase.from("questions").insert([record]);

    if (error) {
      console.error("Failed to save question history:", error.message);
    }
  };

  useEffect(() => {
    const storedSolution = window.localStorage.getItem("math-solver-solution");

    if (!storedSolution) {
      return;
    }

    try {
      const parsedSolution = JSON.parse(storedSolution);
      setSolution(parsedSolution);
    } catch (err) {
      console.warn("Unable to parse stored solution:", err);
    }
  }, []);

  /* ----------------------------
      AUTO GROW TEXTAREA
  -----------------------------*/

  const resizeTextarea = () => {

    if (!textareaRef.current) return;

    textareaRef.current.style.height = "auto";

    textareaRef.current.style.height =
      textareaRef.current.scrollHeight + "px";
  };

  useEffect(() => {
    resizeTextarea();
  }, [question]);

  /* ----------------------------
      ADD FILES
  -----------------------------*/

  const addFiles = (fileList) => {

    const files = Array.from(fileList).filter(file =>
      file.type.startsWith("image/")
    );

    if (!files.length) return;

    setImages(prev => [...prev, ...files]);

    setPreviews(prev => [

      ...prev,

      ...files.map(file => ({
        url: URL.createObjectURL(file),
        name: file.name,
        size: (file.size / 1024).toFixed(1) + " KB"
      }))

    ]);
  };
  /* ----------------------------
      IMAGE UPLOAD
  -----------------------------*/

  const handleImageUpload = (e) => {

    addFiles(e.target.files);

    e.target.value = null;

  };

  /* ----------------------------
      REMOVE IMAGE
  -----------------------------*/

  const removeImage = (index) => {

    setImages(prev =>
      prev.filter((_, i) => i !== index)
    );

    URL.revokeObjectURL(previews[index].url);

    setPreviews(prev =>
      prev.filter((_, i) => i !== index)
    );

  };

  /* ----------------------------
      DRAG & DROP
  -----------------------------*/

  const handleDragOver = (e) => {

    e.preventDefault();

    setDragActive(true);

  };

  const handleDragLeave = (e) => {

    e.preventDefault();

    if (e.currentTarget.contains(e.relatedTarget)) return;

    setDragActive(false);

};

  const handleDrop = (e) => {

    e.preventDefault();

    e.stopPropagation();

    setDragActive(false);

    const files = [...e.dataTransfer.files];

    if (!files.length) return;

    addFiles(files);

};

  /* ----------------------------
      PASTE IMAGE (CTRL + V)
  -----------------------------*/

  useEffect(() => {

    const handlePaste = (event) => {

      const items = event.clipboardData?.items;

      if (!items) return;

      const files = [];

      for (const item of items) {

        if (item.type.startsWith("image")) {

          const file = item.getAsFile();

          if (file) {

            files.push(file);

          }

        }

      }

      if (files.length) {

        addFiles(files);

      }

    };

    window.addEventListener("paste", handlePaste);

    return () => {

      window.removeEventListener("paste", handlePaste);

    };

  }, []);

  /* ----------------------------
      SEND MESSAGE
  -----------------------------*/

  const sendMessage = async () => {

    if (!question.trim() && images.length === 0) {

      alert("Please enter a question or upload an image.");

      return;

    }

    try {

      setLoading(true);
      setSolution(null);

      const formData = new FormData();

      formData.append("question", question);

      images.forEach(file => {

        formData.append("files", file);

      });

      const response = await axios.post(

        API_URL,

        formData,

        {

          headers: {

            "Content-Type": "multipart/form-data"

          }

        }

      );

      if (response.data.error) {

        alert(response.data.error);

        return;

      }

      console.log("[MathSolver] response.data:", response.data);
      setSolution(response.data);
      window.localStorage.setItem(
        "math-solver-solution",
        JSON.stringify(response.data)
      );
      saveHistoryItem(question, response.data);
      setTimeout(() => {
        window.scrollTo({
          top: document.body.scrollHeight,
          behavior: "smooth"
        });
      }, 200);

      setQuestion("");
      setImages([]);
      previews.forEach(img => URL.revokeObjectURL(img.url));
      setPreviews([]);

    }

    catch (err) {

      console.error(err);

      if (err.response) {

        alert(
        err.response?.data?.detail ||
        "Something went wrong."
        );

      }

      else {

        alert("Unable to connect to server.");

      }

    }

    finally {

      setLoading(false);

    }

  };

  /* ----------------------------
      ENTER TO SEND
  -----------------------------*/

  const handleKeyDown = (e) => {

    if (e.key === "Enter" && !e.shiftKey) {

      e.preventDefault();

      sendMessage();

    }

  };
return (
  <main className="app-shell">
    <section className="composer">

      {/* ---------- HERO ---------- */}

      <div className="hero">

        <span className="hero-badge">
          AI Powered
        </span>

        <h1>AI Math Solver</h1>

        <p>
          Solve Mathematics, Physics and Chemistry
          problems with step-by-step explanations.
        </p>

      </div>

      {/* ---------- CHAT BOX ---------- */}

      <div
          className={`chat-composer ${dragActive ? "drag-active" : ""}`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
        >

        <textarea
          ref={textareaRef}
          className="chat-input"
          rows={1}
          placeholder="Ask any Math, Physics or Chemistry question..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
        />

        <div className="composer-footer">

        <label className="image-button">

            <FiImage size={20} />

            <span>Upload</span>

            <input
                hidden
                multiple
                type="file"
                accept="image/*"
                onChange={handleImageUpload}
            />

        </label>
          

          <button
            className="send-button"
            onClick={sendMessage}
            disabled={loading}
          >

            <FiSend size={18} />

            {loading ? " Solving..." : " Solve"}

          </button>

        </div>

      </div>

      {/* ---------- IMAGE PREVIEW ---------- */}

      {previews.length > 0 && (

        <div className="multi-preview-grid">

          {previews.map((item, index) => (

            <div
              key={index}
              className="preview-card"
            >

              <img

                src={item.url}

                alt="preview"

                className="inside-preview-image"

                onClick={() =>
                  setFullscreenImage(item.url)
                }

              />

              <button

                className="remove-image-btn"

                onClick={() =>
                  removeImage(index)
                }

              >

                <FiTrash2 size={16} />

              </button>

              <button

                className="preview-expand"

                onClick={() =>
                  setFullscreenImage(item.url)
                }

              >

                <FiMaximize2 size={16} />

              </button>

              <div className="preview-info">

                <div className="preview-name">

                  {item.name}

                </div>

                <div className="preview-size">

                  {item.size}

                </div>

              </div>

            </div>

          ))}

        </div>

      )}

      {/* ---------- FULL SCREEN ---------- */}

      {fullscreenImage && (

        <div

          className="fullscreen-overlay"

          onClick={() =>
            setFullscreenImage(null)
          }

        >

          <img

            src={fullscreenImage}

            alt="fullscreen"

            className="fullscreen-image"

          />

        </div>

      )}

    </section>


    {loading && (

      <div className="loading">

        <div className="spinner"></div>

        <h2>Thinking...</h2>

        <p>Generating step-by-step solution</p>

      </div>

    )}
{solution?.problems?.length > 0 && (
  <section className="solution-paper">
    {solution.problems.map((problem, problemIndex) => {
      const finalAnswer =
        problem.answer ||
        problem.steps?.[problem.steps.length - 1]?.result ||
        "";

      return (
        <div key={problemIndex} className="problem-card">
          <div className="problem-header">
            <h2>
              {problem.source === "image" ? "Image Problem" : "Text Problem"}
            </h2>
          </div>

          {problem.question && (
            <div className="problem-question">
              <QuestionText question={problem.question} />
            </div>
          )}

          {problem.steps?.map((step, index) => (
            <div key={index} className="solution-step">
              <h3>
                Step {index + 1}
                {step.title ? ` : ${step.title}` : ""}
              </h3>

              {step.explanation && (
                <div className="step-explanation">
                  <MathText text={step.explanation} />
                </div>
              )}

              {step.expression && (
                <div className="display-math">
                  <StepValue value={step.expression} />
                </div>
              )}

              {step.result && step.result !== step.expression && (
                <div className="display-math">
                  <StepValue value={step.result} />
                </div>
              )}
            </div>
          ))}

          <div className="answer-section">
            <div className="boxed-answer">
              <div className="answer-title">Final Answer</div>
              <div className="answer-value">
                <AnswerValue value={finalAnswer} />
              </div>
            </div>
          </div>

          {problem.suggestions?.length > 0 && (
            <div className="suggestions-section">
              <h2>Suggestions</h2>
              <ul>
                {problem.suggestions.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          <hr />
        </div>
      );
    })}
  </section>
)}
  {!loading &&
    (!solution || solution.problems?.length === 0) && (
      <div className="empty-state">
        <h2>Welcome to AI Math Solver</h2>

        <p>
          Type a question or upload an image to get a
          step-by-step solution.
        </p>

        <div className="feature-list">
          <div>Algebra</div>
          <div>Geometry</div>
          <div>Calculus</div>
          <div>Statistics</div>
          <div>Physics</div>
          <div>Chemistry</div>
        </div>
      </div>
    )}

  </main>
);
}
