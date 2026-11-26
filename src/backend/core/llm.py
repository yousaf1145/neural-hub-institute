"""
Shared LLM helper for the new AI features (AI Professor, assessments, skills).

Uses the same fallback order as the syllabus generator:
Gemini -> Groq -> local Ollama. The syllabus generator itself is not changed.
"""
import json
import os
import re

from dotenv import load_dotenv

load_dotenv()

GEMINI_MODEL = "gemini-2.5-flash"
GROQ_MODEL = "openai/gpt-oss-120b"
OLLAMA_MODEL = "phi3"


class LLMUnavailable(RuntimeError):
    """Raised when every model in the fallback chain failed."""


def generate_text(prompt: str, *, max_tokens: int = 2048, temperature: float = 0.4) -> str:
    errors = []

    # 1. Gemini
    try:
        from core.llm_loader import get_gemini_client  # imported lazily: it raises if the key is missing

        res = get_gemini_client().models.generate_content(model=GEMINI_MODEL, contents=prompt)
        if res and res.text:
            return res.text.strip()
    except Exception as e:  # noqa: BLE001 - any failure moves to the next model
        errors.append(f"gemini: {e}")

    # 2. Groq
    try:
        key = os.environ.get("GROQ_API_KEY")
        if key:
            from groq import Groq

            out = Groq(api_key=key).chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = out.choices[0].message.content
            if text:
                return text.strip()
    except Exception as e:  # noqa: BLE001
        errors.append(f"groq: {e}")

    # 3. Local Ollama
    try:
        import ollama

        out = ollama.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": prompt}])
        text = out.get("message", {}).get("content", "")
        if text:
            return text.strip()
    except Exception as e:  # noqa: BLE001
        errors.append(f"ollama: {e}")

    raise LLMUnavailable("; ".join(errors) or "No model returned any text.")


def extract_json(text: str):
    """Pull the first JSON object/array out of a model reply (handles ```json fences)."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = cleaned.find(opener), cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("The AI model did not return valid JSON.")


def generate_json(prompt: str, **kwargs):
    text = generate_text(
        prompt + "\n\nReturn ONLY valid JSON. No markdown fences, no commentary.", **kwargs
    )
    return extract_json(text)
