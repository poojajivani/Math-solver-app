from pathlib import Path
import re

p = Path('main.py')
text = p.read_text(encoding='utf-8')

pattern = re.compile(r'def solve_image_with_ai\(.*?return raw_data\n\n@app\.post\("/chat"\)', re.S)
replacement = '''def solve_image_with_ai(
    image_base64_list: str | list[str],
    instruction: str = ""
) -> dict[str, Any]:
    if isinstance(image_base64_list, str):
        image_base64_list = [image_base64_list]

    prompt = r"""
You are an expert Mathematics, Physics, Chemistry, and Engineering tutor.

Your goal is to solve the user's problem accurately and return a clean, step-by-step solution.

IMPORTANT:
Return ONLY valid JSON.
Do NOT return markdown.
Do NOT return code fences.
Do NOT return any text outside JSON.

JSON FORMAT:
{
  "question": "",
  "problem_type": "",
  "steps": [
    {
      "title": "",
      "explanation": "",
      "expression": "",
      "result": ""
    }
  ],
  "answer": ""
}

Rules:
- Use valid KaTeX for all math.
- Inline math may use $...$.
- Display math may use $$...$$.
- Do NOT wrap expression or result values in $...$.
- If the explanation contains math, wrap it in LaTeX delimiters.
- The answer field must contain only the final answer.
- If you are given typed text plus an image, use the typed text to guide how you interpret the image problem.

If the text is unclear and the image cannot be read, return:
{
  "question": "Unable to read image clearly",
  "problem_type": "ocr_error",
  "steps": [],
  "answer": "Please upload a clearer image"
}
"""

    prompt += f"\nUser Question:\n{instruction.strip() or 'Solve the attached image problem. Answer the math problem shown in the image.'}"

    client = get_ai_client()

    message_content = [
        {
            "type": "text",
            "text": prompt
        }
    ]

    for image_base64 in image_base64_list:
        message_content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_base64}"
                }
            }
        )

    completion = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[
            {
                "role": "user",
                "content": message_content
            }
        ],
        temperature=0
    )

    response_text = completion.choices[0].message.content

    print("========== RAW IMAGE RESPONSE ==========")
    print(response_text)
    print("=======================================")

    raw_data = extract_json_object(response_text)

    for step in raw_data.get("steps", []):
        if not step.get("result", "").strip():
            step["result"] = step.get("expression", "")

    if raw_data.get("steps"):
        for step in reversed(raw_data["steps"]):
            if step.get("result"):
                raw_data["answer"] = step["result"]
                break

    return raw_data

@app.post("/chat")'''

new_text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit(f"Pattern replacement failed, {count} occurrences")
p.write_text(new_text, encoding='utf-8')
print('rewritten solve_image_with_ai')
