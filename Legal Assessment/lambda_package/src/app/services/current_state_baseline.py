from __future__ import annotations
import json, statistics
from pathlib import Path
from typing import Dict, List, Tuple
from rapidfuzz import fuzz

import boto3
import os
import json
BUCKET_NAME = os.getenv("BUCKET_NAME")
s3 = boto3.client('s3')

from ..services.maturity import load_maturity_model
from ..schemas.maturity import Criterion


def _text(ch: Dict) -> str:
    return (ch.get("text") or "")[:4000]

def _source(ch: Dict) -> Dict:
    src = ch.get("source") or {}
    return {"file": src.get("file"), "locator": src.get("locator"),
            "excerpt": (ch.get("text") or "")[:240]}

def _similarity(a: str, b: str) -> int:
    # partial ratio works well for short descriptors vs long chunks
    return fuzz.partial_ratio(a.lower(), b.lower())

def _match_level(descriptor: str, chunks: List[Dict]) -> Tuple[int, List[Dict]]:
    # return best score and the top 3 evidence chunks
    scores = []
    for ch in chunks:
        scores.append((_similarity(descriptor, _text(ch)), ch))
    scores.sort(key=lambda x: x[0], reverse=True)
    top = scores[:3]
    best = top[0][0] if top else 0
    evid = [{"score": s, "source": _source(ch)} for s, ch in top]
    return best, evid

def _filter_chunks(chunks: List[Dict], keywords: List[str]) -> List[Dict]:
    if not keywords:
        return chunks
    kw = [k.lower() for k in keywords]
    out = []
    for ch in chunks:
        t = _text(ch).lower()
        if any(k in t for k in kw):
            out.append(ch)
    # fallback to all if filter too strict
    return out if out else chunks

def _score_criterion(cr: Criterion, chunks: List[Dict]) -> Dict:
    # For each level (1..4), score against chunks; pick highest
    candidates = []
    evid_map = {}
    for lvl, desc in cr.levels.items():
        best, evid = _match_level(desc, chunks)
        candidates.append((lvl, best))
        evid_map[lvl] = evid
    candidates.sort(key=lambda x: x[1], reverse=True)
    pred_level, pred_score = candidates[0]
    return {
        "id": cr.id,
        "label": cr.label,
        "level": int(pred_level),
        "score": int(pred_score),
        "per_level_scores": {int(l): int(s) for l, s in candidates},
        "evidence": evid_map[pred_level],   # evidence for winning level
    }

def _rollup(levels: List[int], method: str) -> int:
    if not levels:
        return 1
    if method == "mean":
        return max(1, min(4, round(sum(levels)/len(levels))))
    return max(1, min(4, int(statistics.median(levels))))

def score_current_state_baseline(company, i, threshold: int = 55, model_path: str | None = None):
    """
    Build current-state levels for every category using fuzzy match to descriptors.
    Writes data/working/{job}/current_state.json
    """
    chunks = json.loads(s3.get_object(Bucket=BUCKET_NAME, Key=f"{company}/chunks.json")['Body'].read().decode('utf-8'))
    model, _ = load_maturity_model(model_path)
    cat = model.categories[i]
    rel_chunks = _filter_chunks(chunks, keywords=[k for cr in cat.criteria for k in cr.keywords])
    crit_results = []
    for cr in cat.criteria:
        crit_chunks = _filter_chunks(rel_chunks, cr.keywords)
        crit_results.append(_score_criterion(cr, crit_chunks))
    levels = [c["level"] for c in crit_results]
    level = _rollup(levels, cat.rollup)
    coverage = (sum(1 for c in crit_results if c["score"] >= threshold) / max(1, len(crit_results)))
    confidence = min(1.0, (sum(c["score"] for c in crit_results) / (100 * max(1, len(crit_results)))))

    return {
        "id": cat.id,
        "name": cat.name,
        "level": level,
        "coverage": round(coverage, 2),
        "confidence": round(confidence, 2),
        "criteria": crit_results
    }