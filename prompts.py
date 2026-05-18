def build_followup_questions_prompt(device_name, intended_use, device_type, rag_context):
    """Build a Stage 1 prompt asking the LLM for device-specific follow-up questions."""

    iso_notes = rag_context.get("iso14971_notes", "")
    relevant_cases = rag_context.get("relevant_cases", [])

    prompt = f"""You are a medical device risk management expert following ISO 14971.

A user is creating a Risk Management File (RMF) for the following device:
- Device Name: {device_name}
- Intended Use: {intended_use}
- Device Type: {device_type}

ISO 14971 Context:
{iso_notes}

Relevant Risk Cases:
{relevant_cases}

Generate 5 to 8 targeted follow-up questions to collect the specific information needed to identify and assess risks for this device. Focus on:
- Operating environment and conditions of use
- Intended patient population and user type
- Known failure modes for this device category
- Safety controls or standards this device must meet
- Critical use scenarios and foreseeable misuse

Output ONLY a JSON array of question strings. No explanation, no markdown, no extra text.

Example format:
["Question 1?", "Question 2?", "Question 3?"]
"""
    return prompt


def build_rmf_generation_prompt(device_name, intended_use, device_type, rag_context, followup_qa=None):
    """Build a Stage 2 prompt asking the LLM to output a JSON RMF risk table."""

    iso_notes = rag_context.get("iso14971_notes", "")
    relevant_cases = rag_context.get("relevant_cases", [])

    if followup_qa:
        qa_lines = []
        for i, item in enumerate(followup_qa, 1):
            q = item.get("question", "")
            a = item.get("answer", "")
            qa_lines.append(f"Q{i}: {q}\nA{i}: {a}")
        qa_section = "\n".join(qa_lines)
    else:
        qa_section = "No additional information provided."

    prompt = f"""You are a medical device risk management expert following ISO 14971.

Generate a Risk Management File (RMF) risk table for the following device:
- Device Name: {device_name}
- Intended Use: {intended_use}
- Device Type: {device_type}

ISO 14971 Context:
{iso_notes}

Relevant Risk Cases:
{relevant_cases}

Device-Specific Information (from follow-up Q&A):
{qa_section}

Output ONLY a JSON array of risk records. No explanation, no markdown, no extra text.

Each record must contain exactly these fields:
- "Hazard": the root cause or hazard source
- "Hazardous Situation": the sequence of events leading to harm
- "Possible Harm": specific harm to patient, user, or environment
- "Severity": High, Medium, or Low
- "Probability": High, Medium, or Low
- "Initial Risk Level": High, Medium, or Low
- "Risk Control Measure": specific design or procedural control
- "Residual Risk": High, Medium, or Low after applying the control
- "Verification Method": how the control measure will be verified
- "Status": Draft

Generate between 5 and 10 risk records covering the most significant hazards.

Example:
[
  {{
    "Hazard": "Incorrect sensor reading",
    "Hazardous Situation": "Device reports normal when patient condition is worsening",
    "Possible Harm": "Delayed diagnosis and treatment",
    "Severity": "High",
    "Probability": "Medium",
    "Initial Risk Level": "High",
    "Risk Control Measure": "Redundant sensor validation and alarm thresholds",
    "Residual Risk": "Low",
    "Verification Method": "Bench testing and clinical validation study",
    "Status": "Draft"
  }}
]
"""
    return prompt
