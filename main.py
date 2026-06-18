from dotenv import load_dotenv
import html
import json
import os
import re
import base64
from typing import Any
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from pydantic import BaseModel, Field
from json_repair import repair_json

# =========================
# LOAD ENV
# =========================

load_dotenv()

# =========================
# FASTAPI APP
# =========================

app = FastAPI(
    title="AI Math Solver",
    description="AI Math Solver with ChatGPT style image + text support",
    version="2.0.0",
)

# =========================
# CORS
# =========================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# GROQ CLIENT
# =========================

def get_ai_client():

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Missing GROQ_API_KEY in .env file"
        )

    return Groq(api_key=api_key)

# =========================
# REQUEST MODEL
# =========================

class SolveRequest(BaseModel):
    question: str = Field(..., min_length=1)

# =========================
# STEP MODEL
# =========================

class SolutionStep(BaseModel):
    title: str
    explanation: str
    expression: str | None = None
    result: str | None = None

# =========================
# RICH TEXT MODEL
# =========================

class RichText(BaseModel):
    markdown: str
    html: str

# =========================
# RESPONSE MODEL
# =========================

class SolveResponse(BaseModel):
    question: str
    answer: str
    steps: list[SolutionStep]
    suggestions: list[str]
    rich_text: RichText

# =========================
# EXTRACT JSON
# =========================
def extract_json_object(text: str) -> dict[str, Any]:

    cleaned = text.strip()

    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned
    )

    match = re.search(
        r"\{.*\}",
        cleaned,
        flags=re.DOTALL
    )

    if match:
        cleaned = match.group(0)

    repaired = repair_json(cleaned)

    return json.loads(repaired)


# =========================
# CLEAN TEXT FUNCTION
# =========================

def clean_text(text: str):

    if not text:
        return ""

    # REMOVE LATEX COMMANDS
    text = re.sub(r"\\[a-zA-Z]+", "", text)

    # REMOVE CURLY BRACES
    text = text.replace("{", "")
    text = text.replace("}", "")

    # REMOVE $
    text = text.replace("$", "")

    # REMOVE BACKSLASHES
    text = text.replace("\\", "")

    # REMOVE MULTIPLE SPACES
    text = re.sub(r"\s+", " ", text)

    return text.strip()

def markdown_to_safe_html(markdown: str) -> str:

    output = []
    in_list = False

    def inline_format(value: str) -> str:

        escaped = html.escape(value)

        escaped = re.sub(
            r"`([^`]+)`",
            r"<code>\1</code>",
            escaped
        )

        escaped = re.sub(
            r"\*\*([^*]+)\*\*",
            r"<strong>\1</strong>",
            escaped
        )

        return escaped

    for line in markdown.splitlines():

        stripped = line.strip()

        if not stripped:
            continue

        if stripped.startswith("- "):

            if not in_list:
                output.append("<ul>")
                in_list = True

            output.append(
                f"<li>{inline_format(stripped[2:])}</li>"
            )

            continue

        if in_list:
            output.append("</ul>")
            in_list = False

        if stripped.startswith("## "):

            output.append(
                f"<h2>{inline_format(stripped[3:])}</h2>"
            )

        elif stripped.startswith("# "):

            output.append(
                f"<h1>{inline_format(stripped[2:])}</h1>"
            )

        else:

            output.append(
                f"<p>{inline_format(stripped)}</p>"
            )

    if in_list:
        output.append("</ul>")

    return "\n".join(output)
def fix_latex_fractions(text: str) -> str:

    if not text:
        return ""

    # Convert simple division to \frac

    text = re.sub(
        r"\((.*?)\)/\((.*?)\)",
        r"\\frac{\1}{\2}",
        text
    )

    return text
# =========================
# NORMALIZE RESPONSE
# =========================

def normalize_solution(
    raw_data: dict[str, Any],
    original_question: str
) -> SolveResponse:

    steps = []

    raw_steps = raw_data.get("steps", [])

    if isinstance(raw_steps, list):

        for step in raw_steps:

            if isinstance(step, dict):

                steps.append(
                    SolutionStep(
                        title=str(step.get("title", "")),

                        explanation=str(
                            step.get("explanation", "")
                        ),

                        expression=fix_latex_fractions(
                            str(step.get("expression", ""))
                        ),

                        result=fix_latex_fractions(
                            str(step.get("result", ""))
                        )
                    )
                )

    answer = fix_latex_fractions(
        str(raw_data.get("answer", ""))
    )

    suggestions = []

    raw_suggestions = raw_data.get("suggestions", [])

    if isinstance(raw_suggestions, list):

        suggestions = [
            str(item)
            for item in raw_suggestions
        ]

    markdown_lines = [
        "# Step By Step Solution",
        "",
    ]

    for index, step in enumerate(steps, start=1):

        markdown_lines.extend([
            f"## Step {index}: {step.title}",
            "",
            step.explanation,
            ""
        ])

        if step.expression:

            markdown_lines.extend([
                f"`{step.expression}`",
                ""
            ])

        if step.result:

            markdown_lines.extend([
                f"Result: **{step.result}**",
                ""
            ])

    markdown_lines.extend([
        "",
        "## Final Answer",
        "",
        f"**{answer}**"
    ])

    if suggestions:

        markdown_lines.extend([
            "",
            "## Suggestions"
        ])

        markdown_lines.extend([
            f"- {item}"
            for item in suggestions
        ])

    markdown = "\n".join(markdown_lines)

    html_output = markdown_to_safe_html(markdown)

    return SolveResponse(
        question=original_question,
        answer=answer,
        steps=steps,
        suggestions=suggestions,
        rich_text=RichText(
            markdown=markdown,
            html=html_output
        )
    )

# =========================
# AI SOLVER
# =========================

def solve_with_ai(question: str) -> SolveResponse:

    prompt = f"""
You are an expert Math, Physics and Chemistry tutor.

Return ONLY valid JSON.

Rules:
1. No markdown outside JSON.
2. No code fences.
3. No extra text.
4. Use valid KaTeX LaTeX.
5. Use \\frac for fractions.
6. expression and result must contain ONLY LaTeX.
7. explanation must be normal readable text.
8. Create 3-8 meaningful steps.
9. Step titles must describe the action.
10. title MUST be plain text only.
11. Never use LaTeX, $, $$, \\, or formulas inside title.
12. Put all mathematical expressions inside expression or result.
JSON Format:

{{
  "answer":"latex answer",
  "steps":[
    {{
  "title":"Differentiate the first function",
  "explanation":"Differentiate $$u(\\theta)=\\sec\\left(\\frac{1}{2}\\theta\\right)$$ using the chain rule.",
  "expression":"u(\\theta)=\\sec\\left(\\frac{1}{2}\\theta\\right)",
  "result":"u'(\\theta)=..."
}}
  ],
  "suggestions":[]
}}

Question:
{question}
"""

    try:

        client = get_ai_client()

        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0,
        )

        response_text = completion.choices[0].message.content

        print(response_text)

        raw_data = extract_json_object(response_text)

        return normalize_solution(
            raw_data,
            question if question else "Image Question"
        )
        

    except Exception as e:

        print(str(e))

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
# =========================
# HOME ROUTE
# =========================

@app.get("/")
def home():

    return {
        "message": "AI Math Solver Running",
        "docs": "/docs"
    }

# =========================
# TEXT SOLVER API
# =========================

@app.post("/solve", response_model=SolveResponse)
def solve_math(request: SolveRequest):

    return solve_with_ai(request.question)

@app.get("/solve", response_model=SolveResponse)
def solve_math_get(
    question: str = Query(..., min_length=1)
):

    return solve_with_ai(question)

# =========================
# CHATGPT STYLE IMAGE + TEXT
# =========================

@app.post("/chat")
async def chat_with_image(
    question: str = Form(""),
    files: list[UploadFile] | None = File(None)
):
    try:

        client = get_ai_client()

        content = []

        # Add user question
        if question.strip():
            content.append({
    "type": "text",
    "text": f"""
You are an expert Math, Physics and Chemistry solver.

Return ONLY valid JSON.

Format:

{{
  "answer":"final answer",
  "steps":[
    {{
      "title":"step",
      "explanation":"explanation",
      "expression":"latex",
      "result":"latex"
    }}
  ],
  "suggestions":[]
}}

User Question:
{question}
"""
})

        # Add all uploaded images
        if files:

            for file in files:

                image_bytes = await file.read()

                image_base64 = base64.b64encode(
                    image_bytes
                ).decode("utf-8")

                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    }
                })

        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": content
                }
            ],
            temperature=0.1,
        )

        response_text = completion.choices[0].message.content

        print(response_text)

        raw_data = extract_json_object(
            response_text
        )

        return normalize_solution(
            raw_data,
            question if question else "Image Question"
        )

    except Exception as e:

        import traceback
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )