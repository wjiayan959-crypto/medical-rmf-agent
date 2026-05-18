import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

ISO_NOTES_PATH = BASE_DIR / "data" / "standards" / "iso14971_notes.txt"
RISK_CASES_PATH = BASE_DIR / "data" / "risk_cases.json"

# Keywords used to detect device type from user input and boost matching cases.
_INFUSION_PUMP_KEYWORDS = {
    "infusion", "pump", "syringe", "iv", "intravenous", "drip",
    "peristaltic", "volumetric", "ders", "drug library", "free-flow",
    "occlusion", "air-in-line", "administration set",
}
_GLUCOSE_METER_KEYWORDS = {
    "glucose", "glucometer", "blood glucose", "blood sugar", "glycemic",
    "glycaemic", "diabetes", "diabetic", "insulin", "hypoglycemia",
    "hypoglycaemia", "hyperglycemia", "hyperglycaemia", "bgm", "smbg",
    "self-monitoring", "test strip", "hba1c", "lancet", "fingerstick",
}


def load_iso14971_notes():
    if not ISO_NOTES_PATH.exists():
        return ""
    with open(ISO_NOTES_PATH, "r", encoding="utf-8") as f:
        return f.read()


def load_risk_cases():
    if not RISK_CASES_PATH.exists():
        return []
    with open(RISK_CASES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _detect_device_type(query: str) -> str | None:
    """
    Return a normalised device-type label if the query matches known keywords,
    or None if no device type can be inferred.
    """
    q = query.lower()
    if any(kw in q for kw in _INFUSION_PUMP_KEYWORDS):
        return "infusion pump"
    if any(kw in q for kw in _GLUCOSE_METER_KEYWORDS):
        return "blood glucose meter"
    return None


def _keyword_score(user_input: str, case: dict) -> int:
    """
    Count how many words from user_input appear in the combined case text.
    Uses all relevant fields from the updated risk_cases.json schema.
    """
    query = user_input.lower()

    case_text = " ".join([
        str(case.get("device_type", "")),
        str(case.get("hazard", "")),
        str(case.get("sequence_of_events", "")),
        str(case.get("hazardous_situation", "")),
        str(case.get("harm", "")),
        str(case.get("risk_control", "")),
        str(case.get("verification_method", "")),
        # Legacy field names — kept for backward compatibility with old JSON entries
        str(case.get("possible_harm", "")),
        str(case.get("suggested_control", "")),
    ]).lower()

    return sum(1 for word in query.split() if word in case_text)


def retrieve_relevant_cases(user_input: str, top_k: int = 5) -> list:
    """
    Retrieve the most relevant risk cases for the given user input.

    Device-type detection: if the query clearly matches an infusion pump or
    blood glucose meter, a large score bonus is applied to cases of that type
    so they consistently rank above unrelated device cases.
    """
    risk_cases = load_risk_cases()
    device_hint = _detect_device_type(user_input)

    scored: list[tuple[int, dict]] = []
    for case in risk_cases:
        score = _keyword_score(user_input, case)

        # Apply device-type priority boost (much larger than keyword overlap).
        # This ensures device-specific cases surface first even when the user
        # query uses high-level terms with low keyword overlap in case text.
        if device_hint and device_hint in case.get("device_type", "").lower():
            score += 20

        if score > 0:
            scored.append((score, case))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [case for _, case in scored[:top_k]]


def build_rag_context(device_name: str, intended_use: str, device_type: str) -> dict:
    """
    Build the RAG context dict passed to the LLM prompt builders.
    Always includes full ISO 14971 notes and device-type-prioritised risk cases.
    """
    iso_notes = load_iso14971_notes()
    query = f"{device_name} {intended_use} {device_type}"
    relevant_cases = retrieve_relevant_cases(query)

    return {
        "iso14971_notes": iso_notes,
        "relevant_cases": relevant_cases,
    }
