from __future__ import annotations
import json, math, re
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from ..services.maturity import load_maturity_model

# OpenAI client - required for this module
try:
    from openai import OpenAI
    import os

    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY environment variable is required")
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    print("Using OpenAI for policy adjudication")
except Exception as e:
    raise RuntimeError(f"OpenAI client initialization failed: {e}")

CHAT_MODEL = "gpt-4o-mini"
EMBED_MODEL = "text-embedding-3-small"


def _load_index(index_path: str | None) -> Dict[str, Any]:
    BASE_DIR = Path(__file__).parent.parent.parent  # services -> app -> src
    p = BASE_DIR / "assets" / "policy_index.json"
    if not p.exists():
        raise FileNotFoundError(f"Policy index not found at {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _embed_query(q: str) -> List[float]:
    """Generate embedding for query using OpenAI API"""
    try:
        resp = client.embeddings.create(model=EMBED_MODEL, input=[q])
        return resp.data[0].embedding
    except Exception as e:
        raise RuntimeError(f"Query embedding generation failed: {e}")


def _cosine(a: List[float], b: List[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a)) or 1.0
    db = math.sqrt(sum(x * x for x in b)) or 1.0
    return num / (da * db)


def _retrieve(idx: Dict[str, Any], query: str, k: int = 5) -> List[Dict[str, Any]]:
    """Retrieve most relevant policy chunks using semantic search"""
    chunks = idx.get("chunks", [])
    engine = (idx.get("meta") or {}).get("engine", "")

    if engine != "openai":
        raise ValueError(f"Policy index was not built with OpenAI embeddings (engine: {engine})")

    qv = _embed_query(query)
    scored = []
    for c in chunks:
        if "embedding" not in c:
            continue
        s = _cosine(qv, c["embedding"])
        scored.append((s, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:k]]


def _build_category_query(cat: Dict[str, Any]) -> str:
    # include category name + criteria labels + current baseline level
    parts = [f"Category: {cat.get('name', cat.get('id', ''))}",
             f"Baseline level: {cat.get('level', '?')}"]
    for cr in cat.get("criteria", [])[:8]:  # cap to keep query compact
        parts.append(f"- {cr.get('label', cr.get('id'))}: L{cr.get('level', '?')}")
    return "\n".join(parts)


def _build_prompt(cat: Dict[str, Any], policy_snippets: List[Dict[str, Any]], maturity_defs: Dict[str, Any]) -> List[
    Dict[str, str]]:
    name = cat.get("name", cat.get("id", ""))
    # try to include the category's criteria/levels definitions from the maturity model (if present)
    defs = []
    # maturity_defs: {"categories":[{id,name,criteria:[{label,levels{1..4}}]}]}
    try:
        md_cat = next((x for x in maturity_defs.get("categories", []) if x.get("id") == cat.get("id")), None)
        if md_cat:
            for cr in md_cat.get("criteria", [])[:6]:
                lv = cr.get("levels", {})
                defs.append(
                    f"{cr.get('label', cr.get('id'))}: L1={lv.get(1, '')}; L2={lv.get(2, '')}; L3={lv.get(3, '')}; L4={lv.get(4, '')}")
    except Exception:
        pass

    pol_text = "\n\n".join(
        [f"[{i + 1}] {s['file']} — {s['id']}\n{(s.get('text') or '')[:900]}" for i, s in enumerate(policy_snippets)])

    sys = (
        "You are a legal operations maturity adjudicator. "
        "Given the company policy excerpts and the baseline assessment, decide the correct level (1-4) for the category. "
        "Be conservative and align strictly with policy. Return ONLY JSON."
    )
    user = (
            f"Category: {name}\n"
            f"Baseline summary:\n{_build_category_query(cat)}\n\n"
            f"Maturity definitions (for reference):\n" + ("\n".join(defs) if defs else "(none)") + "\n\n"
                                                                                                   f"Policy excerpts:\n{pol_text}\n\n"
                                                                                                   "Return JSON: {\"level\": 1|2|3|4, \"confidence\": 0..1, \"reason\": \"short\", \"citations\": [\"chunk-id-1\", ...]}"
    )
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def apply_policy_to_current_state(
        cs,
        index_path: Optional[str] = None,
        model_path: Optional[str] = None,
        top_k: int = 5,
        enforce: bool = False
) -> Path:
    """
    Reads working/{job}/current_state.json and maturity model, retrieves policy snippets,
    asks LLM for policy-aligned level per category, writes working/{job}/current_state_policy.json.
    """

    # raw maturity YAML (as dict) for definitions
    model, raw = load_maturity_model()
    maturity_defs = raw  # {"categories":[...]}

    idx = _load_index(index_path)

    results: List[Dict[str, Any]] = []
    for cat in cs.get("categories", []):
        query = _build_category_query(cat)
        hits = _retrieve(idx, query, k=top_k)

        msgs = _build_prompt(cat, hits, maturity_defs)
        try:
            resp = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=msgs,
                temperature=0,
                response_format={"type": "json_object"}
            )
            data = json.loads(resp.choices[0].message.content)
        except Exception as e:
            raise RuntimeError(f"LLM adjudication failed for category {cat.get('name', cat.get('id', 'unknown'))}: {e}")

        # merge
        cat_out = dict(cat)  # copy
        cat_out["policy_level"] = int(data.get("level", cat.get("level", 1)))
        cat_out["policy_confidence"] = float(data.get("confidence", 0.0))
        cat_out["policy_reason"] = data.get("reason", "")
        cat_out["policy_citations"] = list(map(str, data.get("citations", [])))

        # choose final
        if enforce:
            cat_out["final_level"] = cat_out["policy_level"]
            cat_out["enforced"] = True
        else:
            # simple blending: prefer policy if high confidence, else keep baseline
            base = int(cat.get("level", 1))
            pol = int(cat_out["policy_level"])
            conf = float(cat_out["policy_confidence"])
            cat_out["final_level"] = pol if conf >= 0.7 else base
            cat_out["blended"] = True

        results.append(cat_out)

    out = {
        "engine": "openai",
        "enforce": enforce,
        "categories": results
    }
    return out