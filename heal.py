import os
from concurrent.futures import ThreadPoolExecutor
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


def get_model_config(error_context: str) -> types.GenerateContentConfig:
    complex_triggers = ["Traceback", "RecursionError", "IndexError", "AssertionError", "FAILED"]
    is_complex = any(trigger in error_context for trigger in complex_triggers)
    budget = 1024 if is_complex else 100
    return types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=budget)
    )


def fix_linter():
    if not os.path.exists("main.py") or not os.path.exists("linter_errors.log"):
        return

    with open("main.py", "r") as f:
        code_content = f.read()

    with open("linter_errors.log", "r") as f:
        log_content = f.read()

    if not log_content.strip():
        print("No linter errors found.")
        return

    config = get_model_config(log_content)

    prompt = f"""
    You are an automated code remediation agent.
    Fix all linter and style errors reported in the log for this Python file.

    LINTER LOG:
    {log_content}

    SOURCE CODE (main.py):
    {code_content}

    Return ONLY the raw corrected Python code. Do not include markdown code block formatting or explanations.
    """

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
        config=config,
    )

    clean_code = response.text.replace("```python", "").replace("```", "").strip()

    # Append '\n' at the end to satisfy PEP 8 / W292
    with open("main.py", "w") as f:
        f.write(clean_code + "\n")

    print("Successfully patched main.py using linter_errors.log")


def fix_cve():
    if not os.path.exists("requirements.txt"):
        return

    with open("requirements.txt", "r") as f:
        reqs_content = f.read()

    log_content = ""
    if os.path.exists("cve_errors.log"):
        with open("cve_errors.log", "r") as f:
            log_content = f.read()

    config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=100)
    )

    prompt = f"""
    You are an automated dependency updater and security remediation agent.
    Update the packages in requirements.txt to their secure, stable, non-vulnerable versions.

    SECURITY LOG:
    {log_content}

    REQUIREMENTS (requirements.txt):
    {reqs_content}

    Return ONLY the updated requirements.txt content. Do not include markdown code blocks or explanations.
    """

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
        config=config,
    )

    clean_reqs = response.text.replace("```text", "").replace("```", "").strip()

    # Append '\n' at the end as well
    with open("requirements.txt", "w") as f:
        f.write(clean_reqs + "\n")

    print("Successfully patched requirements.txt")


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=2) as executor:
        t1 = executor.submit(fix_linter)
        t2 = executor.submit(fix_cve)
        t1.result()
        t2.result()