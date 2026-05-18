"""
prompts.py

Prompt builders for the two-stage RMF generation pipeline.

Stage 1  build_followup_questions_prompt  — elicits device-specific clinical
                                           and technical information needed
                                           for rigorous risk analysis.

Stage 2  build_rmf_generation_prompt      — generates a professional ISO 14971-
                                           compliant risk table in JSON format.
"""

# ---------------------------------------------------------------------------
# SHARED SCALE DEFINITIONS (injected into both prompts for consistency)
# ---------------------------------------------------------------------------

_SEVERITY_SCALE = """
SEVERITY SCALE (use exactly these five levels):
  Negligible   — No injury or impact on health; temporary discomfort at most.
  Minor        — Reversible, temporary injury; no medical intervention required.
  Serious      — Injury requiring medical intervention; temporary disability.
  Critical     — Irreversible injury; permanent impairment or significant disability.
  Catastrophic — Death or life-threatening injury.
""".strip()

_PROBABILITY_SCALE = """
PROBABILITY SCALE (use exactly these four levels):
  Remote     — Very unlikely to occur in the device's expected service life.
  Occasional — Unlikely but possible; may occur in a small proportion of uses.
  Probable   — Likely to occur in a significant proportion of uses.
  Frequent   — Expected to occur regularly in normal use conditions.
""".strip()

_RISK_LEVEL_MATRIX = """
RISK LEVEL DETERMINATION (use HIGH / MEDIUM / LOW):
  Catastrophic  + Occasional/Probable/Frequent = HIGH
  Catastrophic  + Remote                       = HIGH
  Critical      + Probable/Frequent            = HIGH
  Critical      + Occasional                   = HIGH
  Critical      + Remote                       = MEDIUM
  Serious       + Probable/Frequent            = HIGH
  Serious       + Occasional                   = MEDIUM
  Serious       + Remote                       = LOW
  Minor         + Probable/Frequent            = MEDIUM
  Minor         + Occasional/Remote            = LOW
  Negligible    + Any                          = LOW
""".strip()


# ---------------------------------------------------------------------------
# STAGE 1 — FOLLOW-UP QUESTIONS
# ---------------------------------------------------------------------------

def build_followup_questions_prompt(
    device_name: str,
    intended_use: str,
    device_type: str,
    rag_context: dict,
) -> str:
    """
    Build a Stage 1 prompt asking the LLM for device-specific follow-up
    questions to elicit the information needed for professional RMF generation.
    """
    iso_notes = rag_context.get("iso14971_notes", "")
    relevant_cases = rag_context.get("relevant_cases", [])

    # Format retrieved cases concisely for context
    case_summary_lines = []
    for i, c in enumerate(relevant_cases, 1):
        hazard = c.get("hazard", c.get("hazard", ""))
        harm = c.get("harm", c.get("possible_harm", ""))
        case_summary_lines.append(f"  {i}. {hazard} → {harm}")
    case_summary = "\n".join(case_summary_lines) if case_summary_lines else "  (none retrieved)"

    prompt = f"""You are a senior medical device risk management specialist with expertise in ISO 14971 risk analysis.

A manufacturer is preparing a Risk Management File (RMF) for the following device:
  Device Name  : {device_name}
  Device Type  : {device_type}
  Intended Use : {intended_use}

RETRIEVED ISO 14971 CONTEXT (use this to inform what information is needed):
{iso_notes[:2000]}

RETRIEVED RISK CASES FOR THIS DEVICE TYPE (reference hazards already known):
{case_summary}

YOUR TASK:
Generate 6 to 8 targeted follow-up questions to collect the specific technical and clinical
information required to perform a rigorous ISO 14971 risk analysis for this device.

Questions should target information gaps that are CRITICAL for:
  1. Identifying device-specific hazard sources not already covered by the retrieved cases
  2. Understanding the intended user population and use environment
  3. Characterising foreseeable misuse scenarios and use errors
  4. Identifying safety-critical software or algorithm functions
  5. Understanding alarm architecture and human factors considerations
  6. Clarifying applicable standards, regulatory classification, and risk acceptability criteria
  7. Understanding any connectivity, data transmission, or cybersecurity functions
  8. Identifying any known limitations or contraindications from predicate devices

Do NOT ask generic questions. Each question must be targeted to the specific device type
and the identified risk gaps. Questions should be answerable by the device design team or
clinical risk manager.

OUTPUT FORMAT:
Output ONLY a valid JSON array of question strings. No explanation. No markdown. No extra text.

Example format:
["Question 1?", "Question 2?", "Question 3?"]
"""
    return prompt


# ---------------------------------------------------------------------------
# STAGE 2 — RMF RISK TABLE GENERATION
# ---------------------------------------------------------------------------

def build_rmf_generation_prompt(
    device_name: str,
    intended_use: str,
    device_type: str,
    rag_context: dict,
    followup_qa: list = None,
) -> str:
    """
    Build a Stage 2 prompt instructing the LLM to generate a professional
    ISO 14971-compliant RMF risk table as a JSON array.
    """
    iso_notes = rag_context.get("iso14971_notes", "")
    relevant_cases = rag_context.get("relevant_cases", [])

    # Format retrieved cases as structured reference material
    case_blocks = []
    for i, c in enumerate(relevant_cases, 1):
        block_lines = [f"Reference Case {i}:"]
        for field in [
            "device_type", "hazard", "sequence_of_events", "hazardous_situation",
            "harm", "initial_severity", "initial_probability", "initial_risk",
            "risk_control", "verification_method",
            "residual_severity", "residual_probability", "residual_risk",
            "residual_risk_acceptability",
        ]:
            val = c.get(field, "")
            if val:
                block_lines.append(f"  {field}: {val}")
        case_blocks.append("\n".join(block_lines))
    cases_text = "\n\n".join(case_blocks) if case_blocks else "(No reference cases retrieved)"

    # Format follow-up Q&A
    if followup_qa:
        qa_lines = []
        for i, item in enumerate(followup_qa, 1):
            q = item.get("question", "").strip()
            a = item.get("answer", "").strip()
            if q:
                qa_lines.append(f"Q{i}: {q}")
                qa_lines.append(f"A{i}: {a if a else '[Not answered]'}")
        qa_section = "\n".join(qa_lines)
    else:
        qa_section = "(No follow-up information provided)"

    prompt = f"""You are a senior medical device risk management specialist with deep expertise in ISO 14971.
Your task is to generate a professional Risk Management File (RMF) risk table for the device described below.
You must reason like an experienced risk manager preparing documentation for regulatory submission.

============================================================
DEVICE INFORMATION
============================================================
Device Name  : {device_name}
Device Type  : {device_type}
Intended Use : {intended_use}

============================================================
ISO 14971 REFERENCE KNOWLEDGE BASE
============================================================
{iso_notes[:3000]}

============================================================
RETRIEVED REFERENCE RISK CASES (use as expert reference, do not copy verbatim)
============================================================
{cases_text}

============================================================
DEVICE-SPECIFIC INFORMATION FROM FOLLOW-UP Q&A
============================================================
{qa_section}

============================================================
RISK ESTIMATION SCALES
============================================================
{_SEVERITY_SCALE}

{_PROBABILITY_SCALE}

{_RISK_LEVEL_MATRIX}

============================================================
GENERATION INSTRUCTIONS
============================================================
Generate between 8 and 12 risk records covering the most clinically significant hazards
for this specific device.

MANDATORY REQUIREMENTS for each record:
1. HAZARD: Identify the root cause or hazard source precisely. Be specific to the device type.
   Do not use vague terms like "device malfunction".

2. HAZARDOUS SITUATION: Describe the complete sequence of events from hazard to patient exposure.
   Format: "[Triggering event] → [Sequence of events] → [Patient or user exposed to hazard]"
   This should be specific and traceable to the device's clinical use context.

3. POSSIBLE HARM: Describe the specific clinical harm to patient, user, or third party.
   State the anatomical or physiological consequence. Do not use vague terms like "patient injury".

4. SEVERITY: Use EXACTLY one of: Negligible / Minor / Serious / Critical / Catastrophic
   Base this on the worst credible harm scenario for this hazardous situation.

5. PROBABILITY: Use EXACTLY one of: Remote / Occasional / Probable / Frequent
   Estimate probability considering the intended use environment and user population.

6. INITIAL RISK LEVEL: Use EXACTLY one of: LOW / MEDIUM / HIGH
   Derived from the risk matrix above (Severity × Probability).

7. RISK CONTROL MEASURE: Describe specific, implementable controls following ISO 14971 priority:
   FIRST — Inherent safety by design (preferred): hardware interlocks, fail-safe design, physical guards
   SECOND — Protective measures: alarms, alerts, software dose limits, automatic shut-off
   THIRD — Information for safety: IFU warnings, labeling, training (least effective; supplement only)
   Controls must be specific and measurable. Do NOT list "staff training" as a sole control for
   significant risks. Each control must be clearly implementable and verifiable.

8. RESIDUAL RISK: Use EXACTLY one of: LOW / MEDIUM / HIGH
   This is the risk level AFTER all risk controls in field 7 are applied.
   Justify the reduction: controls must logically reduce the severity or probability.

9. VERIFICATION METHOD: State specific, measurable verification activities appropriate for
   regulatory documentation. Examples: "Flow accuracy testing per IEC 60601-2-24",
   "Summative usability evaluation per IEC 62366 with 15 nurse participants",
   "Air detection sensitivity testing at 0.1 mL bubble volume", "Software fault injection
   testing per IEC 62304 Class C requirements". Do NOT use vague terms like "testing" or "review".

10. STATUS: Always output "Draft"

CONTENT QUALITY REQUIREMENTS:
- Cover BOTH normal use AND foreseeable misuse hazards
- Include hazards from all categories: hardware, software, human factors, environment, alarms
- Avoid duplicate hazards — each record must address a distinct hazardous situation
- Risk controls must be logically connected to the specific hazard identified
- Residual risk must reflect a realistic reduction achievable by the stated controls
- Do not invent hazards that are irrelevant to the specific device type
- Use clinical and technical terminology appropriate for regulatory submissions

OUTPUT FORMAT:
Output ONLY a valid JSON array. No markdown code fences. No explanation. No extra text.
Begin with [ and end with ].

Each record must use EXACTLY these field names:
{{
  "Hazard": "...",
  "Hazardous Situation": "...",
  "Possible Harm": "...",
  "Severity": "...",
  "Probability": "...",
  "Initial Risk Level": "...",
  "Risk Control Measure": "...",
  "Residual Risk": "...",
  "Verification Method": "...",
  "Status": "Draft"
}}
"""
    return prompt
