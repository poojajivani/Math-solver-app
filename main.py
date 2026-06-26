from dotenv import load_dotenv
import html
import json
import os
import re
import base64
import ast
from typing import Any
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from pydantic import BaseModel, Field
from json_repair import repair_json
import sympy as sp
from sympy import symbols, Eq, solve, sympify, summation
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
    convert_xor,
)

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

class ProblemSolution(BaseModel):
    source: str
    question: str
    answer: str
    steps: list[SolutionStep]

class MultiSolveResponse(BaseModel):
    problems: list[ProblemSolution]

# =========================
# EXTRACT JSON
# =========================
def extract_json_object(text: str) -> dict[str, Any]:

    if not text:
        raise ValueError("AI returned empty response")

    cleaned = text.strip()

    if not cleaned:
        raise ValueError("AI returned blank response")

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

    text = str(text)

    # remove bad \f
    text = text.replace("\f", "")

    # remove double slash
    text = text.replace("\\\\frac", "\\frac")

    text = text.replace("\\\\sqrt", "\\sqrt")
    text = text.replace("\\\\sum", "\\sum")
    text = text.replace("\\\\int", "\\int")
    text = text.replace("*", r"\times ")
    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    text = text.replace("(x^(n+1))/(n+1)", r"\frac{x^{n+1}}{n+1}")
    text = text.replace("∫", r"\int ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(
        r'([a-zA-Z0-9]+)\^([0-9]+)',
        r'\1^{\2}',
        text
    )
    text = re.sub(
        r'(\d+)\\sin',
        r'\1 \\times \\sin',
        text
    )

    text = re.sub(
        r'(\d+)\\cos',
        r'\1 \\times \\cos',
        text
    )

    text = re.sub(
        r'(\d+)\\tan',
        r'\1 \\times \\tan',
        text
    )

    return text

def clean_explanation(text):

    if not text:
        return ""

    return str(text).strip()
# =========================
# NORMALIZE RESPONSE
# =========================

def normalize_solution(
    raw_data: dict[str, Any],
    original_question: str
) -> SolveResponse:

    if isinstance(raw_data, list):
        raw_data = raw_data[0]

    if not isinstance(raw_data, dict):
        raise HTTPException(
            status_code=500,
            detail=f"Expected dict, got {type(raw_data)}"
        )

    steps = []

    raw_steps = raw_data.get("steps", [])

    if isinstance(raw_steps, list):

        for step in raw_steps:

            if isinstance(step, dict):

                steps.append(
                    SolutionStep(
                        title=str(step.get("title", "")),

                        explanation=clean_explanation(
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


        answer = ""

        if steps and steps[-1].result:
            answer = steps[-1].result
        else:
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


def fix_known_summation(problem):

    q = str(problem.get("question", "")).replace(" ", "")

    return problem

SYMPY_TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)

SYMPY_LOCALS = {
    "x": sp.Symbol("x"),
    "y": sp.Symbol("y"),
    "z": sp.Symbol("z"),
    "t": sp.Symbol("t"),
    "a": sp.Symbol("a"),
    "b": sp.Symbol("b"),
    "c": sp.Symbol("c"),
    "pi": sp.pi,
    "e": sp.E,
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "sec": sp.sec,
    "csc": sp.csc,
    "cot": sp.cot,
    "asin": sp.asin,
    "acos": sp.acos,
    "atan": sp.atan,
    "log": sp.log,
    "ln": sp.log,
    "sqrt": sp.sqrt,
    "abs": sp.Abs,
}


def sympy_latex(value: Any) -> str:

    if isinstance(value, str):
        return value

    if isinstance(value, list):
        return ", ".join(sympy_latex(item) for item in value)

    return sp.latex(value)


def build_local_response(
    question: str,
    answer: Any,
    steps: list[dict[str, str]],
    problem_type: str
) -> SolveResponse:

    raw_data = {
        "question": question,
        "problem_type": problem_type,
        "steps": steps,
        "answer": sympy_latex(answer),
        "suggestions": []
    }

    return normalize_solution(raw_data, question)


def normalize_user_math(text: str) -> str:

    text = str(text).strip()
    text = text.replace("−", "-")
    text = text.replace("–", "-")
    text = text.replace("×", "*")
    text = text.replace("÷", "/")
    text = text.replace("√", "sqrt")
    text = text.replace("$", "")
    text = text.replace("\\pi", "pi")
    text = text.replace("\\theta", "theta")
    text = text.replace("\\sin", "sin")
    text = text.replace("\\cos", "cos")
    text = text.replace("\\tan", "tan")
    text = text.replace("\\log", "log")
    text = text.replace("\\ln", "ln")
    text = text.replace("\\sqrt", "sqrt")
    return text.strip()


def parse_math_expression(text: str):

    value = normalize_user_math(text)
    value = re.sub(r"^(?:find|solve|evaluate|calculate|compute)\s+", "", value, flags=re.IGNORECASE)
    value = value.strip(" :;.")

    return parse_expr(
        value,
        local_dict=SYMPY_LOCALS,
        transformations=SYMPY_TRANSFORMATIONS,
        evaluate=True
    )


def parse_math_expression_unevaluated(text: str):

    value = normalize_user_math(text)
    value = re.sub(r"^(?:find|solve|evaluate|calculate|compute)\s+", "", value, flags=re.IGNORECASE)
    value = value.strip(" :;.")

    return parse_expr(
        value,
        local_dict=SYMPY_LOCALS,
        transformations=SYMPY_TRANSFORMATIONS,
        evaluate=False
    )


def expression_after_keyword(question: str, keywords: list[str]) -> str:

    text = normalize_user_math(question)

    for keyword in keywords:
        pattern = rf"\b{re.escape(keyword)}\b(?:\s+of)?\s*"
        match = re.search(pattern, text, flags=re.IGNORECASE)

        if match:
            return text[match.end():].strip(" :;.")

    return text.strip(" :;.")


def first_symbol(expr, default: str = "x"):

    symbols_found = sorted(expr.free_symbols, key=lambda item: item.name)

    if symbols_found:
        return symbols_found[0]

    return sp.Symbol(default)


def solve_equation_locally(question: str) -> SolveResponse | None:

    if "=" not in question:
        return None

    text = normalize_user_math(question)
    text = re.sub(r"^(?:solve|find)\s+", "", text, flags=re.IGNORECASE).strip(" .")
    left_text, right_text = text.split("=", 1)

    left_expr = parse_math_expression(left_text)
    right_expr = parse_math_expression(right_text)
    variable = first_symbol(left_expr - right_expr)
    equation = Eq(left_expr, right_expr)
    solutions = solve(equation, variable)
    answer = (
        Eq(variable, solutions[0], evaluate=False)
        if len(solutions) == 1
        else [Eq(variable, solution, evaluate=False) for solution in solutions]
    )
    answer_latex = sympy_latex(answer)

    steps = [
        {
            "title": "Write the equation",
            "explanation": "Convert the input into a symbolic equation.",
            "expression": sympy_latex(equation),
            "result": sympy_latex(equation)
        },
        {
            "title": f"Solve for {variable}",
            "explanation": f"Use algebraic solving to isolate ${sp.latex(variable)}$.",
            "expression": sympy_latex(equation),
            "result": answer_latex
        }
    ]

    return build_local_response(question, answer, steps, "equation")


def solve_derivative_locally(question: str) -> SolveResponse | None:

    if not re.search(r"\b(derivative|differentiate|d/d[a-z])\b", question, flags=re.IGNORECASE):
        return None

    variable_match = re.search(r"\bd/d([a-z])\b|with respect to\s+([a-z])|wrt\s+([a-z])", question, flags=re.IGNORECASE)
    variable = sp.Symbol(next(group for group in variable_match.groups() if group) if variable_match else "x")
    expression_text = expression_after_keyword(question, ["derivative", "differentiate"])
    expression_text = re.sub(r"^(?:of\s+)?", "", expression_text, flags=re.IGNORECASE)
    expression_text = re.sub(r"\b(?:with respect to|wrt)\s+[a-z]\b", "", expression_text, flags=re.IGNORECASE)
    expression_text = re.sub(r"^d/d[a-z]\s*", "", expression_text, flags=re.IGNORECASE)
    expr = parse_math_expression(expression_text)
    result = sp.diff(expr, variable)

    steps = [
        {
            "title": "Identify the function",
            "explanation": f"Differentiate with respect to ${sp.latex(variable)}$.",
            "expression": sympy_latex(expr),
            "result": sympy_latex(expr)
        },
        {
            "title": "Differentiate",
            "explanation": "Apply the derivative rules and simplify.",
            "expression": f"\\frac{{d}}{{d{sp.latex(variable)}}}\\left({sympy_latex(expr)}\\right)",
            "result": sympy_latex(result)
        }
    ]

    return build_local_response(question, result, steps, "derivative")


def solve_integral_locally(question: str) -> SolveResponse | None:

    if not re.search(r"\b(integral|integrate)\b|∫", question, flags=re.IGNORECASE):
        return None

    variable_match = re.search(r"\bd([a-z])\b|with respect to\s+([a-z])|wrt\s+([a-z])", question, flags=re.IGNORECASE)
    variable = sp.Symbol(next(group for group in variable_match.groups() if group) if variable_match else "x")
    expression_text = expression_after_keyword(question, ["integral", "integrate"])
    expression_text = expression_text.replace("∫", "")
    expression_text = re.sub(r"\b(?:with respect to|wrt)\s+[a-z]\b", "", expression_text, flags=re.IGNORECASE)
    expression_text = re.sub(r"\bd[a-z]\b", "", expression_text, flags=re.IGNORECASE).strip()
    expr = parse_math_expression(expression_text)
    result = sp.integrate(expr, variable)

    steps = [
        {
            "title": "Identify the integrand",
            "explanation": f"Integrate with respect to ${sp.latex(variable)}$.",
            "expression": sympy_latex(expr),
            "result": sympy_latex(expr)
        },
        {
            "title": "Integrate",
            "explanation": "Apply integration rules.",
            "expression": f"\\int {sympy_latex(expr)}\\,d{sp.latex(variable)}",
            "result": f"{sympy_latex(result)} + C"
        }
    ]

    return build_local_response(question, f"{sympy_latex(result)} + C", steps, "integral")


def solve_limit_locally(question: str) -> SolveResponse | None:

    if not re.search(r"\blimit\b|\\lim", question, flags=re.IGNORECASE):
        return None

    text = normalize_user_math(question)
    match = re.search(
        r"limit(?:\s+of)?\s+(.+?)\s+as\s+([a-z])\s+(?:approaches|goes to|->|=)\s+(.+)$",
        text,
        flags=re.IGNORECASE
    )

    if not match:
        return None

    expression_text, variable_text, target_text = match.groups()
    variable = sp.Symbol(variable_text)
    expr = parse_math_expression(expression_text)
    target = parse_math_expression(target_text)
    result = sp.limit(expr, variable, target)

    steps = [
        {
            "title": "Identify the limit",
            "explanation": f"Let ${sp.latex(variable)}$ approach ${sympy_latex(target)}$.",
            "expression": f"\\lim_{{{sp.latex(variable)}\\to {sympy_latex(target)}}} {sympy_latex(expr)}",
            "result": sympy_latex(result)
        }
    ]

    return build_local_response(question, result, steps, "limit")


def solve_matrix_locally(question: str) -> SolveResponse | None:

    if "[" not in question or not re.search(r"\b(matrix|determinant|inverse|transpose|rank)\b", question, flags=re.IGNORECASE):
        return None

    matrix_match = re.search(r"\[\s*\[.*\]\s*\]", question)

    if not matrix_match:
        return None

    matrix_data = ast.literal_eval(matrix_match.group(0))
    matrix = sp.Matrix(matrix_data)

    if re.search(r"\bdeterminant|det\b", question, flags=re.IGNORECASE):
        operation = "determinant"
        result = matrix.det()
    elif re.search(r"\binverse\b", question, flags=re.IGNORECASE):
        operation = "inverse"
        result = matrix.inv()
    elif re.search(r"\btranspose\b", question, flags=re.IGNORECASE):
        operation = "transpose"
        result = matrix.T
    elif re.search(r"\brank\b", question, flags=re.IGNORECASE):
        operation = "rank"
        result = matrix.rank()
    else:
        operation = "matrix"
        result = matrix

    steps = [
        {
            "title": "Read the matrix",
            "explanation": f"Apply the requested {operation} operation.",
            "expression": sympy_latex(matrix),
            "result": sympy_latex(result)
        }
    ]

    return build_local_response(question, result, steps, "matrix")


def solve_statistics_locally(question: str) -> SolveResponse | None:

    if not re.search(r"\b(mean|median|mode|variance|standard deviation|std|statistics)\b", question, flags=re.IGNORECASE):
        return None

    numbers = [
        sp.Rational(item)
        for item in re.findall(r"-?\d+(?:\.\d+)?", question)
    ]

    if not numbers:
        return None

    sorted_numbers = sorted(numbers)
    count = len(numbers)
    mean_value = sp.simplify(sum(numbers) / count)

    if count % 2:
        median_value = sorted_numbers[count // 2]
    else:
        median_value = sp.simplify((sorted_numbers[count // 2 - 1] + sorted_numbers[count // 2]) / 2)

    frequencies = {number: numbers.count(number) for number in set(numbers)}
    highest_frequency = max(frequencies.values())
    modes = sorted([number for number, frequency in frequencies.items() if frequency == highest_frequency])
    variance_value = sp.simplify(sum((number - mean_value) ** 2 for number in numbers) / count)
    std_value = sp.sqrt(variance_value)

    if re.search(r"\bmedian\b", question, flags=re.IGNORECASE):
        operation = "median"
        answer = median_value
    elif re.search(r"\bmode\b", question, flags=re.IGNORECASE):
        operation = "mode"
        answer = modes
    elif re.search(r"\bvariance\b", question, flags=re.IGNORECASE):
        operation = "variance"
        answer = variance_value
    elif re.search(r"\bstandard deviation|std\b", question, flags=re.IGNORECASE):
        operation = "standard deviation"
        answer = std_value
    else:
        operation = "mean"
        answer = mean_value

    steps = [
        {
            "title": "List the data",
            "explanation": "Use the numeric values from the question.",
            "expression": sympy_latex(numbers),
            "result": sympy_latex(sorted_numbers)
        },
        {
            "title": f"Find the {operation}",
            "explanation": f"Calculate the requested {operation}.",
            "expression": sympy_latex(numbers),
            "result": sympy_latex(answer)
        }
    ]

    return build_local_response(question, answer, steps, "statistics")


def solve_polynomial_locally(question: str) -> SolveResponse | None:

    if not re.search(r"\b(polynomial|roots?|zeros?|degree)\b", question, flags=re.IGNORECASE):
        return None

    if re.search(r"\broot|zero\b", question, flags=re.IGNORECASE):
        expression_text = expression_after_keyword(question, ["roots", "root", "zeros", "zero", "polynomial"])
        expression_text = re.sub(r"^of\s+", "", expression_text, flags=re.IGNORECASE).strip()
        expression_text = re.sub(r"^polynomial\s+", "", expression_text, flags=re.IGNORECASE).strip()
        expr = parse_math_expression(expression_text)
        variable = first_symbol(expr)
        factored_expr = sp.factor(expr)
        roots = solve(Eq(expr, 0), variable)

        steps = [
            {
                "title": "Identify the polynomial",
                "explanation": "Start with the polynomial from the question.",
                "expression": sympy_latex(expr),
                "result": sympy_latex(expr)
            },
            {
                "title": "Set the polynomial equal to zero",
                "explanation": "The roots are the values that make the polynomial equal zero.",
                "expression": f"{sympy_latex(expr)} = 0",
                "result": f"{sympy_latex(expr)} = 0"
            }
        ]

        if factored_expr != expr:
            steps.append({
                "title": "Factor the polynomial",
                "explanation": "Rewrite the polynomial as a product of simpler factors.",
                "expression": f"{sympy_latex(expr)} = 0",
                "result": f"{sympy_latex(factored_expr)} = 0"
            })

        for root in roots:
            steps.append({
                "title": f"Solve for {variable}",
                "explanation": "Set a factor equal to zero and solve.",
                "expression": f"{sp.latex(variable)} = {sympy_latex(root)}",
                "result": f"{sp.latex(variable)} = {sympy_latex(root)}"
            })

        steps.append({
            "title": "List the roots",
            "explanation": "Collect all values that satisfy the polynomial equation.",
            "expression": sympy_latex(roots),
            "result": sympy_latex(roots)
        })

        return build_local_response(question, roots, steps, "polynomial")

    if re.search(r"\bdegree\b", question, flags=re.IGNORECASE):
        expression_text = expression_after_keyword(question, ["degree", "polynomial"])
        expression_text = re.sub(r"^of\s+", "", expression_text, flags=re.IGNORECASE).strip()
        expression_text = re.sub(r"^polynomial\s+", "", expression_text, flags=re.IGNORECASE).strip()
        expr = parse_math_expression(expression_text)
        variable = first_symbol(expr)
        degree = sp.Poly(expr, variable).degree()

        steps = [
            {
                "title": "Find the highest power",
                "explanation": f"The degree is the highest exponent of ${sp.latex(variable)}$.",
                "expression": sympy_latex(expr),
                "result": sympy_latex(degree)
            }
        ]

        return build_local_response(question, degree, steps, "polynomial")

    return None


def latex_signed_terms(terms: list[sp.Expr]) -> str:

    pieces = []

    for term in terms:
        if term.could_extract_minus_sign():
            piece = sympy_latex(-term)
            pieces.append(f"- {piece}" if not pieces else f" - {piece}")
        else:
            piece = sympy_latex(term)
            pieces.append(piece if not pieces else f" + {piece}")

    return "".join(pieces)


def latex_preserve_add_order(expr: sp.Expr) -> str:

    if expr.is_Add:
        return latex_signed_terms(list(expr.args))

    return sympy_latex(expr)


def build_simplify_steps(original_expr: sp.Expr, unevaluated_expr: sp.Expr, result: sp.Expr) -> list[dict[str, str]]:

    visible_expression = latex_preserve_add_order(unevaluated_expr)
    final_result = sympy_latex(result)

    steps = [
        {
            "title": "Write the expression",
            "explanation": "Start by writing the expression exactly as an algebra expression.",
            "expression": visible_expression,
            "result": visible_expression
        },
        {
            "title": "Remove extra parentheses",
            "explanation": (
                "Parentheses that are not changing signs or multiplying anything can be removed. "
                "This lets us see all the terms clearly."
            ),
            "expression": visible_expression,
            "result": visible_expression
        }
    ]

    symbols_in_expr = sorted(unevaluated_expr.free_symbols, key=lambda item: item.name)

    if len(symbols_in_expr) == 1 and unevaluated_expr.is_Add:
        variable = symbols_in_expr[0]
        variable_terms = []
        constant_terms = []

        for term in unevaluated_expr.args:
            coefficient, exponent = term.as_coeff_exponent(variable)

            if exponent == 1:
                variable_terms.append(coefficient)
            elif exponent == 0:
                constant_terms.append(term)

        if variable_terms:
            coefficient_sum = sp.Add(*variable_terms)
            constant_sum = sp.Add(*constant_terms) if constant_terms else 0
            coefficient_latex = latex_signed_terms(variable_terms)
            combined_expression = (
                f"\\left({coefficient_latex}\\right){sp.latex(variable)}"
                f"{' + ' + sympy_latex(constant_sum) if constant_sum else ''}"
            )

            steps.append({
                "title": "Combine like terms",
                "explanation": (
                    f"The terms containing ${sp.latex(variable)}$ are like terms, so combine their coefficients."
                ),
                "expression": visible_expression,
                "result": combined_expression
            })

            steps.append({
                "title": "Simplify the coefficient",
                "explanation": (
                    "Add and subtract the coefficients. If the coefficient becomes 0, that variable term disappears."
                ),
                "expression": combined_expression,
                "result": final_result
            })
            return steps

    if original_expr != result:
        steps.append({
            "title": "Simplify",
            "explanation": "Now combine any like terms and reduce the expression as much as possible.",
            "expression": sympy_latex(original_expr),
            "result": final_result
        })
    else:
        steps.append({
            "title": "Check the expression",
            "explanation": "There are no more like terms or arithmetic operations to simplify.",
            "expression": sympy_latex(original_expr),
            "result": final_result
        })

    return steps


def solve_expression_operation_locally(question: str) -> SolveResponse | None:

    operation_match = re.search(
        r"\b(factor|expand|simplify|evaluate|calculate|compute)\b",
        question,
        flags=re.IGNORECASE
    )
    expression_text = question

    if operation_match:
        operation = operation_match.group(1).lower()
        expression_text = expression_after_keyword(question, [operation])
    else:
        operation = "simplify"

    expr = parse_math_expression(expression_text)
    unevaluated_expr = parse_math_expression_unevaluated(expression_text)

    if operation == "factor":
        result = sp.factor(expr)
    elif operation == "expand":
        result = sp.expand(expr)
    else:
        result = sp.simplify(expr)

    if operation == "simplify":
        steps = build_simplify_steps(expr, unevaluated_expr, result)
    else:
        steps = [
            {
                "title": operation.capitalize(),
                "explanation": f"Apply SymPy {operation} rules.",
                "expression": sympy_latex(expr),
                "result": sympy_latex(result)
            }
        ]

    return build_local_response(question, result, steps, operation)


def solve_with_local_math(question: str) -> SolveResponse | None:

    if not question or not question.strip():
        return None

    solvers = [
        solve_statistics_locally,
        solve_matrix_locally,
        solve_derivative_locally,
        solve_integral_locally,
        solve_limit_locally,
        solve_equation_locally,
        solve_polynomial_locally,
        solve_expression_operation_locally,
    ]

    for solver in solvers:
        try:
            result = solver(question)

            if result:
                return result

        except Exception as error:
            print(f"LOCAL SOLVER SKIPPED {solver.__name__}: {error}")

    return None

def solve_with_ai(question: str) -> SolveResponse:

    local_result = solve_with_local_math(question)

    if local_result:
        return local_result

    prompt = f"""
    You are an expert Mathematics, Physics, Chemistry, and Engineering tutor.

    Your goal is to solve the user's problem accurately and return a clean, step-by-step solution.

    IMPORTANT:
    Return ONLY valid JSON.
    Return JSON only.
    Inside JSON strings you may use LaTeX wrapped with $...$ or $$...$$.
    Do NOT return code fences.
    Do NOT return any text outside JSON.

    ====================================
    JSON FORMAT
    ====================================

    {{
    "question": "",
    "problem_type": "",
    "steps": [
        {{
        "title": "",
        "explanation": "",
        "expression": "",
        "result": ""
        }}
    ],
    "answer": ""
    }}

    Explanation Rules:

    - Explanations may contain text and math.
    - Inline math must use $...$
    - Display equations must use $$...$$
    - Never write math as:
      x^(n+1)/(n+1)

    - Always write math as:
    $$\frac{{x^{{n+1}}}}{{n+1}}$$
    ====================================
    GENERAL RULES
    ====================================
    Bad:
    The summation is \sum_{{n=1}}^{{100}}n

    Good:

    The summation is:

    $$
    \sum_{{n=1}}^{{100}}n
    $$

    1. Solve the actual question.
    2. Never guess missing information.
    3. Use correct mathematics.
    4. Show enough steps.
    5. Keep explanations short and clear.
    6. Inline math must use $...$
    7. Never return HTML.
    8. Inline math must use $...$.
    9. Never return triple backticks.
    10. Never duplicate steps.

    If explanation contains mathematical expressions,
        wrap them using Markdown LaTeX.

        Example:

        We need to evaluate

        $$
        \sum_{{x=4}}^{{7}}3x^3
        $$

        by expanding it.
    ====================================
    IMAGE RULES
    ====================================

    When solving from an image:

    - Carefully read all symbols.
    - Recognize:
    - Fractions
    - Powers
    - Roots
    - Summations
    - Integrals
    - Matrices
    - Limits
    - Logarithms
    - Trigonometric functions
    - Graph questions
    - Statistics questions
    For expression and result:

    Do NOT wrap LaTeX with $...$

    GOOD:
    "4\\sum_{{n=1}}^{{100}}n + \\sum_{{n=1}}^{{100}}5"

    BAD:
    "$4\\sum_{{n=1}}^{{100}}n + \\sum_{{n=1}}^{{100}}5$"

    Do NOT invent symbols.

    If text is unclear:

    {{
    "question":"Unable to read image clearly",
    "problem_type":"ocr_error",
    "steps":[],
    "answer":"Please upload a clearer image"
    }}

    ====================================
    LATEX RULES
    ====================================

    All mathematical expressions MUST be valid KaTeX.

    Use:

    \frac{{a}}{{b}}
    \sqrt{{x}}
    x^2
    x^3
    \pi
    \theta
    \sin(x)
    \cos(x)
    \tan(x)
    \log(x)
    \ln(x)
    \sum
    \int

    Examples:

    Correct:
    "\frac{{17}}{{9}}"

    Correct:
    "50\sin\left(\frac{{(t-5)\pi}}{{20}}\right)"

    Correct:
    "\sum_{{x=4}}^{{7}}3x^3"

    Wrong:
    "17/9"

    Wrong:
    "sin((t-5)pi/20)"

    Wrong:
    "\f\frac"

    Wrong:
    "\\f"

    Wrong:
    "\\rightight"

    Wrong:
    "\\leftleft"

    ====================================
    STEP RULES
    ====================================

    Every step must contain:

    title
    explanation
    expression
    result

    Example:

    {{
    "title":"Subtract 4",
    "explanation":"Subtract 4 from both sides.",
    "expression":"9x+4-4=21-4",
    "result":"9x=17"
    }}

    ====================================
    ALGEBRA RULES
    ====================================

    For equations:

    Solve completely.

    Example:

    2x+25=36

    Answer:

    x=\frac{{11}}{{2}}

    Do not stop early.

    ====================================
    FRACTION RULES
    ====================================

    Always use:

    \frac{{a}}{{b}}

    Never use:

    a/b

    Example:

    Correct:
    "\frac{{11}}{{2}}"

    Wrong:
    "11/2"

    ====================================
    POWER RULES
    ====================================

    Use:

    x^2
    x^3
    a^{{10}}

    Never write:

    x2
    x3

    ====================================
    SUMMATION RULES
    ====================================

    Example:

    \sum_{{x=4}}^{{7}}3x^3

    Expand correctly:

    3(4)^3
    3(5)^3
    3(6)^3
    3(7)^3

    Compute:

    192
    375
    648
    1029

    Final:

    2244

    Answer field:

    "2244"

    Do NOT return the sigma expression again.

    ====================================
    TRIGONOMETRY RULES
    ====================================

    Keep trigonometric expressions on ONE line.

    Correct:

    50\sin\left(\frac{{(t-5)\pi}}{{20}}\right)

    Correct:

    450+50\sin\left(\frac{{(t-5)\pi}}{{20}}\right)

    Wrong:

    50
    \sin(...)

    Wrong:

    450+50
    \sin(...)

    ====================================
    FUNCTION ANALYSIS RULES
    ====================================

    If asked for:

    Amplitude

    Maximum

    Minimum

    Period

    Midline

    Domain

    Range

    Find exactly what is requested.

    Example:

    h(t)=450+50\sin\left(\frac{{(t-5)\pi}}{{20}}\right)

    Amplitude = 50

    Maximum = 500

    Minimum = 400

    Midline = 450

    Range = [400,500]

    ====================================
    CALCULUS RULES
    ====================================

    For derivatives:

    Use proper notation.

    Example:

    \frac{{d}}{{dx}}(x^2)=2x

    For integrals:

    Use proper notation.

    Example:

    \int x^2dx=\frac{{x^3}}{{3}}+C

    ====================================
    MATRIX RULES
    ====================================

    Show matrix operations step-by-step.

    ====================================
    PHYSICS RULES
    ====================================

    Show:

    Formula
    Substitution
    Calculation
    Answer

    Include units.

    ====================================
    CHEMISTRY RULES
    ====================================

    Balance equations when needed.

    Show calculations clearly.

    In explanation:
    - Normal text is allowed.
    - Mathematical expressions must be wrapped using LaTeX delimiters.

    Example:

    "The power rule states that:

    $$
    \int x^n dx = \frac{{x^{{n+1}}}}{{n+1}}+C
    $$

    where n ≠ -1."

    ====================================
    ANSWER RULES
    ====================================

    The answer field MUST contain ONLY the final answer.

    GOOD:

    "x=\frac{{17}}{{9}}"

    GOOD:

    "2244"

    GOOD:

    "500"

    GOOD:

    "Amplitude=50"

    BAD:

    "Let's solve this"

    BAD:

    "Original equation is"

    BAD:

    "9x+4=21"

    BAD:

    "\sum_{{x=4}}^{{7}}3x^3"

    BAD:

    "h(t)=450+50\sin(...)"

    ====================================
    RENDERING RULES
    ====================================

    Every expression must be valid KaTeX.

    No broken LaTeX.

    No raw slash fractions.

    No malformed commands.

    No duplicated expressions.

    ====================================
    FINAL RULE
    ====================================

    Return ONLY valid JSON.
    Solve the problem completely.
    Use valid KaTeX-compatible LaTeX.
    The answer field must contain the final solved result only.

    {question}
    """
    try:

        client = get_ai_client()
        print("PROMPT CREATED SUCCESSFULLY")
        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
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
        print("========== RAW RESPONSE ==========")
        print(response_text)
        print("==================================")

        raw_data = extract_json_object(response_text)

        for step in raw_data.get("steps", []):
            if not step.get("result", "").strip():
                step["result"] = step.get("expression", "")


        if "problems" in raw_data:

            raw_data["problems"] = [
                fix_known_summation(problem)
                for problem in raw_data["problems"]
            ]

        print("RAW DATA:")
        print(json.dumps(raw_data, indent=2))

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


def solve_image_with_ai(
    image_base64: str,
    instruction: str = ""
):
    try:
        client = get_ai_client()

        prompt = f"""
        You are an expert Mathematics, Physics, Chemistry, and Engineering tutor.

        Your goal is to solve the user's problem accurately and return a clean, step-by-step solution.

        IMPORTANT:
        Return ONLY valid JSON.
        Do NOT return markdown.
        Do NOT return code fences.
        Do NOT return any text outside JSON.

        ====================================
        JSON FORMAT
        ====================================
        Bad:
            The summation is \sum_{{n=1}}^{{100}}n

        Good:

            The summation is:

            $$
            \sum_{{n=1}}^{{100}}n
            $$

        Explanation Rules:

        - Explanations may contain text and math.
        - Inline math must use $...$
        - Display equations must use $$...$$
        - Never write math as:
        x^(n+1)/(n+1)

        - Always write math as:
        $$\frac{{x^{{n+1}}}}{{n+1}}$$
        
        {{
        "question": "",
        "problem_type": "",
        "steps": [
            {{
            "title": "",
            "explanation": "",
            "expression": "",
            "result": ""
            }}
        ],
        "answer": ""
        }}
        For expression and result:

        Do NOT wrap LaTeX with $...$

        GOOD:
        "4\\sum_{{n=1}}^{{100}}n + \\sum_{{n=1}}^{{100}}5"

        BAD:
        "$4\\sum_{{n=1}}^{{100}}n + \\sum_{{n=1}}^{{100}}5$"
        ====================================
        GENERAL RULES
        ====================================

        1. Solve the actual question.
        2. Never guess missing information.
        3. Use correct mathematics.
        4. Show enough steps.
        5. Keep explanations short and clear.
        6. Return ONLY JSON.
        7. Never return HTML.
        8. Never return Markdown.
        9. Never return triple backticks.
        10. Never duplicate steps.

        If explanation contains mathematical expressions,
        wrap them using Markdown LaTeX.

        Example:

        We need to evaluate

        $$
        \sum_{{x=4}}^{{7}}3x^3
        $$

        by expanding it.

        ====================================
        IMAGE RULES
        ====================================
        In explanation:
        - Normal text is allowed.
        - Mathematical expressions must be wrapped using LaTeX delimiters.

        Example:

        "The power rule states that:

        $$
        \int x^n dx = \frac{{x^{{n+1}}}}{{n+1}}+C
        $$

        where n ≠ -1."
        When solving from an image:

        - Carefully read all symbols.
        - Recognize:
        - Fractions
        - Powers
        - Roots
        - Summations
        - Integrals
        - Matrices
        - Limits
        - Logarithms
        - Trigonometric functions
        - Graph questions
        - Statistics questions

        Do NOT invent symbols.

        If text is unclear:

        {{
        "question":"Unable to read image clearly",
        "problem_type":"ocr_error",
        "steps":[],
        "answer":"Please upload a clearer image"
        }}

        ====================================
        LATEX RULES
        ====================================

        All mathematical expressions MUST be valid KaTeX.

        Use:

        \frac{{a}}{{b}}
        \sqrt{{x}}
        x^2
        x^3
        \pi
        \theta
        \sin(x)
        \cos(x)
        \tan(x)
        \log(x)
        \ln(x)
        \sum
        \int

        Examples:

        Correct:
        "\frac{{17}}{{9}}"

        Correct:
        "50\sin\left(\frac{{(t-5)\pi}}{{20}}\right)"

        Correct:
        "\sum_{{x=4}}^{{7}}3x^3"

        Wrong:
        "17/9"

        Wrong:
        "sin((t-5)pi/20)"

        Wrong:
        "\f\frac"

        Wrong:
        "\\f"

        Wrong:
        "\\rightight"

        Wrong:
        "\\leftleft"

        ====================================
        STEP RULES
        ====================================

        Every step must contain:

        title
        explanation
        expression
        result

        Example:

        {{
        "title":"Subtract 4",
        "explanation":"Subtract 4 from both sides.",
        "expression":"9x+4-4=21-4",
        "result":"9x=17"
        }}

        ====================================
        ALGEBRA RULES
        ====================================

        For equations:

        Solve completely.

        Example:

        2x+25=36

        Answer:

        x=\frac{{11}}{{2}}

        Do not stop early.

        ====================================
        FRACTION RULES
        ====================================

        Always use:

        \frac{{a}}{{b}}

        Never use:

        a/b

        Example:

        Correct:
        "\frac{{11}}{{2}}"

        Wrong:
        "11/2"

        ====================================
        POWER RULES
        ====================================

        Use:

        x^2
        x^3
        a^{{10}}

        Never write:

        x2
        x3

        ====================================
        SUMMATION RULES
        ====================================

        Example:

        \sum_{{x=4}}^{{7}}3x^3

        Expand correctly:

        3(4)^3
        3(5)^3
        3(6)^3
        3(7)^3

        Compute:

        192
        375
        648
        1029

        Final:

        2244

        Answer field:

        "2244"

        Do NOT return the sigma expression again.

        ====================================
        TRIGONOMETRY RULES
        ====================================

        Keep trigonometric expressions on ONE line.

        Correct:

        50\sin\left(\frac{{(t-5)\pi}}{{20}}\right)

        Correct:

        450+50\sin\left(\frac{{(t-5)\pi}}{{20}}\right)

        Wrong:

        50
        \sin(...)

        Wrong:

        450+50
        \sin(...)

        ====================================
        FUNCTION ANALYSIS RULES
        ====================================

        If asked for:

        Amplitude

        Maximum

        Minimum

        Period

        Midline

        Domain

        Range

        Find exactly what is requested.

        Example:

        h(t)=450+50\sin\left(\frac{{(t-5)\pi}}{{20}}\right)

        Amplitude = 50

        Maximum = 500

        Minimum = 400

        Midline = 450

        Range = [400,500]

        ====================================
        CALCULUS RULES
        ====================================

        For derivatives:

        Use proper notation.

        Example:

        \frac{{d}}{{dx}}(x^2)=2x

        For integrals:

        Use proper notation.

        Example:

        \int x^2dx=\frac{{x^3}}{{3}}+C

        ====================================
        MATRIX RULES
        ====================================

        Show matrix operations step-by-step.

        ====================================
        PHYSICS RULES
        ====================================

        Show:

        Formula
        Substitution
        Calculation
        Answer

        Include units.

        ====================================
        CHEMISTRY RULES
        ====================================

        Balance equations when needed.

        Show calculations clearly.

        ====================================
        ANSWER RULES
        ====================================

        The answer field MUST contain ONLY the final answer.

        GOOD:

        "x=\frac{{17}}{{9}}"

        GOOD:

        "2244"

        GOOD:

        "500"

        GOOD:

        "Amplitude=50"

        BAD:

        "Let's solve this"

        BAD:

        "Original equation is"

        BAD:

        "9x+4=21"

        BAD:

        "\sum_{{x=4}}^{{7}}3x^3"

        BAD:

        "h(t)=450+50\sin(...)"

        ====================================
        RENDERING RULES
        ====================================

        Every expression must be valid KaTeX.

        No broken LaTeX.

        No raw slash fractions.

        No malformed commands.

        No duplicated expressions.

        OCR RULES

        If the extracted question contains missing spaces,
        restore normal English spacing.

        Wrong:
        Writetheequation10x−28y=56inslope−interceptform.

        Correct:
        Write the equation 10x − 28y = 56 in slope-intercept form.

        ====================================
        FINAL RULE
        ====================================

        Return ONLY valid JSON.
        Solve the problem completely.
        Use valid KaTeX-compatible LaTeX.
        The answer field must contain the final solved result only.

       """
        prompt += f"\nUser Question:\n{instruction}"
    except Exception as e:
        print("IMAGE AI ERROR:")
        print(str(e))
        raise e
    completion = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ],
        temperature=0
    )

    response_text = completion.choices[0].message.content

    print("========== RAW RESPONSE ==========")
    print(response_text)
    print("==================================")

    raw_data = extract_json_object(response_text)

    # Force answer = last step result
    if raw_data.get("steps"):

        for step in reversed(raw_data["steps"]):

            if step.get("result"):

                raw_data["answer"] = step["result"]
                break

    return raw_data

@app.post("/chat")
async def chat_with_image(
    question: str = Form(""),
    files: list[UploadFile] | None = File(None)
):
    print("CHAT API HIT")
    print("QUESTION =", question)
    
    try:
        problems = []

        if question.strip() and not files:
            try:
                result = solve_with_ai(question)
                print("SUCCESS")
                print(result)

            except Exception as e:
                print("ERROR IN solve_with_ai")
                print(str(e))
                raise e

            problems.append({
                "source": "text",
                "question": result.question,
                "answer": result.answer,
                "steps": result.steps
            })

        if files:
            for file in files:
                image_bytes = await file.read()

                image_base64 = base64.b64encode(
                    image_bytes
                ).decode("utf-8")

                image_result = solve_image_with_ai(
                    image_base64,
                    question
                )
                image_result["question"] = clean_ocr_text(
                    image_result.get("question", "")
                )

                image_result["question"] = fix_latex_fractions(
                    image_result.get("question", "")
                )

                image_result["answer"] = fix_latex_fractions(
                    image_result.get("answer", "")
                )

                for step in image_result.get("steps", []):
                    step["expression"] = fix_latex_fractions(
                        step.get("expression", "")
                    )

                    step["result"] = fix_latex_fractions(
                        step.get("result", "")
                    )
                    
                problems.append({
                    "source":"image",
                    "question":image_result.get("question",""),
                    "answer": image_result.get("answer", ""),
                    "steps": image_result.get("steps", [])
                })

        return {"problems": problems}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

def clean_ocr_text(text: str) -> str:
    if not text:
        return ""

    text = str(text)
    protected: list[str] = []

    def protect(match):
        protected.append(match.group(0))
        return f"@@@{len(protected) - 1}@@@"

    # Keep LaTeX untouched. The spacing fixes below are for OCR prose and can
    # otherwise corrupt commands such as \sin into \s in.
    text = re.sub(r"\$\$.*?\$\$|\$.*?\$|\\\(.+?\\\)|\\\[.+?\\\]|\\[a-zA-Z]+", protect, text)

    # Space between lowercase and uppercase
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)

    # Space between letters and numbers
    text = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', text)
    text = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', text)

    # Space after punctuation
    text = re.sub(r'([.,;:!?])([A-Za-z])', r'\1 \2', text)

    phrase_fixes = [
        (r"Giventhematrices", "Given the matrices "),
        (r"shownbelow", " shown below"),
        (r"\bAandB\b", "A and B"),
        (r"\b([A-Z])and\s+([A-Z])\b", r"\1 and \2"),
        (r"\b([A-Z])and([A-Z])\b", r"\1 and \2"),
        (r"find([A-Z])", r"find \1"),
        (r"\s*-\s*", " - "),
    ]

    for pattern, replacement in phrase_fixes:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # Space before keywords
    keywords = [
        "in", "find", "solve", "write", "graph",
        "evaluate", "simplify", "factor",
        "equation", "form", "slope",
        "intercept", "answer"
    ]

    for word in keywords:
        text = re.sub(rf'\b({word})\b', r'\1', text, flags=re.IGNORECASE)

    text = re.sub(r'\s+', ' ', text)

    for index, value in enumerate(protected):
        text = text.replace(f"@@@{index}@@@", value)

    return text.strip()
