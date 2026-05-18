import json
import os
from pathlib import Path

import pandas as pd
import requests

from retrieval import build_rag_context
from prompts import build_followup_questions_prompt, build_rmf_generation_prompt

_PROJECT_ROOT = Path(__file__).resolve().parent

def _read_env_file(path):
    """Minimal .env parser used when python-dotenv is not installed."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ[key] = value  # always overwrite so .env updates take effect
    except OSError:
        pass


_DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
_DEEPSEEK_MODEL = "deepseek-chat"


def get_deepseek_api_key():
    """
    Return DEEPSEEK_API_KEY from the environment.

    Re-reads .env / llm_api.env on every call (override=True) so that
    updating the file takes effect without restarting Streamlit.
    Raises ValueError if the key is absent in all sources.
    """
    try:
        from dotenv import load_dotenv as _load_dotenv
        for _env_name in (".env", "llm_api.env"):
            _env_path = _PROJECT_ROOT / _env_name
            if _env_path.exists():
                _load_dotenv(dotenv_path=_env_path, override=True)
    except ImportError:
        for _env_name in (".env", "llm_api.env"):
            _env_path = _PROJECT_ROOT / _env_name
            if _env_path.exists():
                _read_env_file(_env_path)

    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError(
            "DEEPSEEK_API_KEY is not set. "
            "Add it to a .env or llm_api.env file in the project root, "
            "or export it as an environment variable."
        )
    return key


def call_llm(prompt):
    """
    Send a prompt to DeepSeek and return the plain-text response.

    Raises ValueError for a missing API key.
    Raises RuntimeError for API errors or an empty response.
    """

    api_key = get_deepseek_api_key()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": _DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }

    try:
        response = requests.post(
            _DEEPSEEK_API_URL,
            headers=headers,
            json=payload,
            timeout=60,
        )
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"DeepSeek API request failed: {exc}") from exc

    if response.status_code != 200:
        raise RuntimeError(
            f"DeepSeek API returned status {response.status_code}: {response.text}"
        )

    data = response.json()

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(
            f"Unexpected DeepSeek API response structure: {data}"
        ) from exc

    if not text or not text.strip():
        raise RuntimeError("DeepSeek API returned an empty response.")

    return text.strip()


def estimate_risk_level(severity, probability):
    """
    Estimate initial risk level based on severity and probability.
    根据严重性和发生概率估计初始风险等级。
    """

    risk_matrix = {
        ("High", "High"): "High",
        ("High", "Medium"): "High",
        ("High", "Low"): "Medium",
        ("Medium", "High"): "High",
        ("Medium", "Medium"): "Medium",
        ("Medium", "Low"): "Low",
        ("Low", "High"): "Medium",
        ("Low", "Medium"): "Low",
        ("Low", "Low"): "Low",
    }
    # Simple 3x3 risk matrix
    # 简化版 3x3 风险矩阵

    return risk_matrix.get((severity, probability), "Medium")


def mock_llm_generate_rmf_records(device_name, intended_use, device_type, rag_context):
    """
    Mock LLM function for generating RMF records.
    模拟 LLM 生成 RMF 风险记录。

    This version does not call a real API.
    这个版本不会真正调用 API。
    """

    relevant_cases = rag_context.get("relevant_cases", [])
    # Get retrieved cases
    # 获取检索到的风险案例

    records = []
    # Store generated risk records
    # 存放生成的风险记录

    if relevant_cases:
        # If relevant cases are found, generate records based on them
        # 如果找到相关案例，就基于案例生成风险记录

        for case in relevant_cases:
            severity = "High"
            probability = "Medium"
            initial_risk_level = estimate_risk_level(severity, probability)

            record = {
                "Hazard": case.get("hazard", ""),
                "Hazardous Situation": case.get("hazardous_situation", ""),
                "Possible Harm": case.get("possible_harm", ""),
                "Severity": severity,
                "Probability": probability,
                "Initial Risk Level": initial_risk_level,
                "Risk Control Measure": case.get("suggested_control", ""),
                "Residual Risk": "Medium after control",
                "Verification Method": "Design verification, clinical review, and user validation",
                "Status": "Draft - Human review required"
            }

            records.append(record)

    else:
        # If no relevant case is found, generate a generic draft record
        # 如果没有找到相关案例，就生成一个通用风险记录

        severity = "Medium"
        probability = "Medium"
        initial_risk_level = estimate_risk_level(severity, probability)

        record = {
            "Hazard": "Potential device malfunction",
            "Hazardous Situation": f"{device_name} may not perform as intended during use",
            "Possible Harm": "Delayed diagnosis, incorrect treatment, or user confusion",
            "Severity": severity,
            "Probability": probability,
            "Initial Risk Level": initial_risk_level,
            "Risk Control Measure": "Design verification, user instructions, warning system, and performance testing",
            "Residual Risk": "Low to Medium after control",
            "Verification Method": "Bench testing, usability testing, and expert review",
            "Status": "Draft - Human review required"
        }

        records.append(record)

    return records


def generate_rmf_table(device_name, intended_use, device_type):
    """
    Main function for generating RMF table.
    生成 RMF 风险表格的主函数。
    """

    rag_context = build_rag_context(device_name, intended_use, device_type)
    # Build RAG context
    # 构建 RAG 上下文

    prompt = build_rmf_generation_prompt(
        device_name,
        intended_use,
        device_type,
        rag_context
    )
    # Build LLM prompt
    # 构建 LLM 提示词

    records = mock_llm_generate_rmf_records(
        device_name,
        intended_use,
        device_type,
        rag_context
    )
    # Generate RMF records
    # 生成 RMF 风险记录

    df = pd.DataFrame(records)
    # Convert records into table
    # 转换成表格格式

    return df, prompt, rag_context


def _parse_json_response(raw_text):
    """Strip markdown code fences and return a parsed JSON object."""

    text = raw_text.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]                          # drop opening ```json or ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]                     # drop closing ```
        text = "\n".join(lines).strip()

    # If the LLM added prose before the JSON array/object, skip to it
    if not text.startswith(("[", "{")):
        start = min(
            (text.find(c) for c in ("[", "{") if text.find(c) != -1),
            default=-1
        )
        if start != -1:
            text = text[start:]

    return json.loads(text)


_FALLBACK_QUESTIONS = [
    "What is the intended patient population (age range, clinical condition)?",
    "Where will the device be used (hospital ICU, home, outpatient clinic)?",
    "Who are the intended users (trained clinicians, patients, caregivers)?",
    "What are the most critical functions the device must perform correctly?",
    "What are the foreseeable failure modes or misuse scenarios for this device?",
    "What regulatory standards or certifications must this device comply with?",
    "What happens clinically if the device fails or provides incorrect output?",
]


def generate_followup_questions(device_name, intended_use, device_type):
    """
    Stage 1: ask the LLM for device-specific follow-up questions.

    Returns (questions, rag_context, raw_response).
    Falls back to _FALLBACK_QUESTIONS if the response cannot be parsed.
    """

    rag_context = build_rag_context(device_name, intended_use, device_type)

    prompt = build_followup_questions_prompt(
        device_name, intended_use, device_type, rag_context
    )

    raw_response = call_llm(prompt)

    try:
        questions = _parse_json_response(raw_response)
        if not isinstance(questions, list) or not all(isinstance(q, str) for q in questions):
            raise ValueError("Parsed value is not a list of strings.")
    except (json.JSONDecodeError, ValueError):
        questions = list(_FALLBACK_QUESTIONS)

    return questions, rag_context, raw_response


def generate_rmf_from_answers(device_name, intended_use, device_type, followup_qa):
    """
    Stage 2: ask the LLM for a structured RMF risk table.

    followup_qa is a list of dicts: [{"question": "...", "answer": "..."}, ...]

    Returns (DataFrame, rag_context, raw_response).
    Raises RuntimeError if the response cannot be parsed as a JSON array.
    """

    rag_context = build_rag_context(device_name, intended_use, device_type)

    prompt = build_rmf_generation_prompt(
        device_name, intended_use, device_type, rag_context, followup_qa
    )

    raw_response = call_llm(prompt)

    try:
        records = _parse_json_response(raw_response)
        if not isinstance(records, list):
            raise ValueError("Parsed value is not a list.")
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(
            f"Stage 2 LLM returned unparseable JSON.\n"
            f"Parse error: {exc}\n\n"
            f"Raw response:\n{raw_response}"
        ) from exc

    df = pd.DataFrame(records)

    return df, rag_context, raw_response