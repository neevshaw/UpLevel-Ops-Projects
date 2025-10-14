import os, json, re
from pathlib import Path
from typing import Dict, List, Optional
from io import BytesIO

from ..schemas.extraction import ExtractionResult, PainPoint, CurrentTool, ProcessStep, Metric, Opportunity

# OpenAI client - required for this module
try:
    from openai import OpenAI
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY environment variable is required")
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=60)
    print("Using LLM")
except Exception as e:
    raise RuntimeError(f"OpenAI client initialization failed: {e}")

MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

def _first_sentence(text: str, max_len: int = 240) -> str:
    s = re.split(r"(?<=[.!?])\s+", text.strip())
    out = s[0] if s else text.strip()
    return out[:max_len]

def _llm_extract_one(chunk: Dict) -> Dict[str, List[Dict]]:
    """Extract information using LLM in JSON mode"""
    print("Extracting with LLM")
    text = chunk.get("text", "").strip()
    src = chunk.get("source", {})

    messages = [
        {"role": "system", "content": (
            "You are a precise information extractor for legal operations assessments. "
            "Return ONLY JSON matching the schema; do not add commentary."
        )},
        {"role": "user", "content": (
            "Extract pain points, tools, processes, metrics, and opportunities from the text.\n"
            "Use concise phrasing, no hallucinations. If none found, return empty arrays.\n\n"
            f"TEXT:\n{text}"
        )},
    ]

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        data = json.loads(content) if content else {}
    except Exception as e:
        print(e)
        raise RuntimeError(f"LLM extraction failed: {e}")

    # Normalize any strings → dicts so Pydantic validation won't explode
    def _coerce_item(it, kind: str) -> Optional[Dict]:
        if isinstance(it, dict):
            return it
        if isinstance(it, str):
            s = it.strip()
            if not s:
                return None
            if kind == "pain_points":
                return {"text": s, "impact_hint": "med", "effort_hint": "med"}
            if kind == "current_tools":
                return {"name": s}
            if kind == "processes":
                return {"process_name": "Unspecified", "step": s}
            if kind == "metrics":
                return {"name": s}
            if kind == "opportunities":
                return {"area": "General", "description": s, "impact_hint": "med", "effort_hint": "med", "dependencies": []}
        # Unsupported type → drop
        return None
    keys = ["pain_points", "current_tools", "processes", "metrics", "opportunities"]
    if not isinstance(data, dict):
        data = {}
    for k in keys:
        raw_list = data.get(k, [])
        if not isinstance(raw_list, list):
            raw_list = []
        norm: List[Dict] = []
        for it in raw_list:
            coerced = _coerce_item(it, k)
            if coerced is not None:
                norm.append(coerced)
        data[k] = norm  # now guaranteed list-of-dicts
    # Attach source_ref to each item
    source_ref = {
        "file": src.get("file", ""),
        "locator": src.get("locator", ""),
        "excerpt": text[:240] if text else None,
    }
    for k in keys:
        for item in data.get(k, []):
            item["source_ref"] = source_ref  # safe: item is dict
    # Validate with Pydantic
    validated = ExtractionResult(
        chunks_used=[chunk.get("id", "")],
        pain_points=[PainPoint(**p) for p in data.get("pain_points", [])],
        current_tools=[CurrentTool(**t) for t in data.get("current_tools", [])],
        processes=[ProcessStep(**p) for p in data.get("processes", [])],
        metrics=[Metric(**m) for m in data.get("metrics", [])],
        opportunities=[Opportunity(**o) for o in data.get("opportunities", [])],
    )
    return validated.dict()

def extract_from_chunks(chunks, max_chunks: int = 50) -> Path:
    """Read working/{job_id}/chunks.json (new) or working/{job_id}_chunks.json (legacy)."""

    

    results = {
        "pain_points": [],
        "current_tools": [],
        "processes": [],
        "metrics": [],
        "opportunities": [],
        "chunks_used": []
    }

    for i, ch in enumerate(chunks[:max_chunks]):
        out = _llm_extract_one(ch)
        results["chunks_used"].extend(out.get("chunks_used", [ch.get("id","")]))
        for k in ["pain_points","current_tools","processes","metrics","opportunities"]:
            results[k].extend(out.get(k, []))

    return results