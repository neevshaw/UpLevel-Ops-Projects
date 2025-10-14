from __future__ import annotations
import json, re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


IMPACT_MAP = {"low": 1, "med": 2, "high": 3}
# Lower effort = higher score
EFFORT_MAP = {"high": 1, "med": 2, "low": 3}

def _norm_key(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s]", "", s)
    return s

def _first(s: List[str]) -> str | None:
    for x in s:
        if x:
            return x
    return None

def synthesize(data, top_n: int = 8) -> Path:
    """
    Read working/{job_id}/extractions.json -> write working/{job_id}/synthesis.json
    Dedupe similar items, compute Impact×Effort priority scores, return output path.
    """

    pains = data.get("pain_points", [])
    opps  = data.get("opportunities", [])
    tools = data.get("current_tools", [])
    procs = data.get("processes", [])
    mets  = data.get("metrics", [])

    # --- Aggregate Pain Points ---
    pain_buckets: Dict[str, Dict] = {}
    for p in pains:
        text = p.get("text", "").strip()
        key = _norm_key(text)
        if not key:
            continue
        bucket = pain_buckets.setdefault(key, {
            "text": text,
            "category": p.get("category"),
            "impact_hint": p.get("impact_hint", "med"),
            "effort_hint": p.get("effort_hint", "med"),
            "evidence_samples": [],
            "sources": [],
            "count": 0,
        })
        bucket["count"] += 1
        if p.get("evidence"):
            bucket["evidence_samples"].append(p["evidence"])
        src = p.get("source_ref") or {}
        bucket["sources"].append({
            "file": src.get("file"),
            "locator": src.get("locator"),
            "excerpt": src.get("excerpt"),
        })

    # score pains
    for b in pain_buckets.values():
        impact = IMPACT_MAP.get(str(b.get("impact_hint", "med")).lower(), 2)
        effort = EFFORT_MAP.get(str(b.get("effort_hint", "med")).lower(), 2)
        score = impact + effort
        if b["count"] >= 3:
            score += 1
        b["priority_score"] = score

    # --- Aggregate Opportunities ---
    opp_buckets: Dict[str, Dict] = {}
    for o in opps:
        desc = o.get("description", "").strip()
        key = _norm_key(desc)
        if not key:
            continue
        bucket = opp_buckets.setdefault(key, {
            "area": o.get("area") or "General",
            "description": desc,
            "impact_hint": o.get("impact_hint", "med"),
            "effort_hint": o.get("effort_hint", "med"),
            "dependencies": list(o.get("dependencies", []) or []),
            "sources": [],
            "count": 0,
        })
        bucket["count"] += 1
        src = o.get("source_ref") or {}
        bucket["sources"].append({
            "file": src.get("file"),
            "locator": src.get("locator"),
            "excerpt": src.get("excerpt"),
        })

    for b in opp_buckets.values():
        impact = IMPACT_MAP.get(str(b.get("impact_hint", "med")).lower(), 2)
        effort = EFFORT_MAP.get(str(b.get("effort_hint", "med")).lower(), 2)
        score = impact + effort
        if b["count"] >= 3:
            score += 1
        b["priority_score"] = score

    # --- Aggregate Tools ---
    tool_buckets: Dict[str, Dict] = {}
    for t in tools:
        name = (t.get("name") or "").strip()
        if not name:
            continue
        key = _norm_key(name)
        b = tool_buckets.setdefault(key, {
            "name": name,
            "purposes": [],
            "adoption_levels": Counter(),
            "issues": set(),
            "sources": [],
            "count": 0,
        })
        b["count"] += 1
        if t.get("purpose"):
            b["purposes"].append(t["purpose"])
        if t.get("adoption_level"):
            b["adoption_levels"][t["adoption_level"]] += 1
        for issue in (t.get("issues") or []):
            if issue:
                b["issues"].add(issue)
        src = t.get("source_ref") or {}
        b["sources"].append({
            "file": src.get("file"),
            "locator": src.get("locator"),
            "excerpt": src.get("excerpt"),
        })
    # finalize tool buckets
    for b in tool_buckets.values():
        b["issues"] = sorted(b["issues"])
        b["purpose"] = _first(b["purposes"])  # pick first seen
        b["adoption_level"] = (b["adoption_levels"].most_common(1)[0][0]
                               if b["adoption_levels"] else None)
        del b["purposes"], b["adoption_levels"]

    # --- Aggregate Processes ---
    proc_buckets: Dict[str, Dict] = {}
    for p in procs:
        pname = (p.get("process_name") or "Unspecified").strip()
        key = _norm_key(pname)
        b = proc_buckets.setdefault(key, {
            "process_name": pname,
            "steps": [],
            "owners": set(),
            "systems": set(),
            "risks": set(),
            "sources": [],
            "count": 0,
        })
        b["count"] += 1
        if p.get("step"):
            b["steps"].append(p["step"])
        for o in (p.get("owners") or []):
            if o: b["owners"].add(o)
        for s in (p.get("systems") or []):
            if s: b["systems"].add(s)
        for r in (p.get("risks") or []):
            if r: b["risks"].add(r)
        src = p.get("source_ref") or {}
        b["sources"].append({
            "file": src.get("file"),
            "locator": src.get("locator"),
            "excerpt": src.get("excerpt"),
        })
    for b in proc_buckets.values():
        b["steps"]   = b["steps"][:20]
        b["owners"]  = sorted(b["owners"])
        b["systems"] = sorted(b["systems"])
        b["risks"]   = sorted(b["risks"])

    # --- Aggregate Metrics ---
    metric_buckets: Dict[str, Dict] = {}
    for m in mets:
        name = (m.get("name") or "").strip()
        if not name:
            continue
        key = _norm_key(name)
        b = metric_buckets.setdefault(key, {
            "name": name,
            "values": [],
            "timeframes": Counter(),
            "owners": Counter(),
            "sources": [],
            "count": 0,
        })
        b["count"] += 1
        if m.get("value"):     b["values"].append(m["value"])
        if m.get("timeframe"): b["timeframes"][m["timeframe"]] += 1
        if m.get("owner"):     b["owners"][m["owner"]] += 1
        src = m.get("source_ref") or {}
        b["sources"].append({
            "file": src.get("file"),
            "locator": src.get("locator"),
            "excerpt": src.get("excerpt"),
        })
    for b in metric_buckets.values():
        b["sample_value"] = _first(b["values"])
        b["timeframe"] = (b["timeframes"].most_common(1)[0][0]
                          if b["timeframes"] else None)
        b["owner"] = (b["owners"].most_common(1)[0][0]
                      if b["owners"] else None)
        del b["values"], b["timeframes"], b["owners"]

    # --- Top priorities (pains + opps) ---
    priority_items = []
    for b in pain_buckets.values():
        priority_items.append({
            "kind": "pain_point",
            "text": b["text"],
            "score": b["priority_score"],
            "count": b["count"],
            "sources": b["sources"][:3],
        })
    for b in opp_buckets.values():
        priority_items.append({
            "kind": "opportunity",
            "text": b["description"],
            "score": b["priority_score"],
            "count": b["count"],
            "sources": b["sources"][:3],
        })
    priority_items.sort(key=lambda x: (x["score"], x["count"]), reverse=True)
    top_priorities = priority_items[:top_n]

    out = {
        "counts": {
            "pain_points": len(pain_buckets),
            "opportunities": len(opp_buckets),
            "tools": len(tool_buckets),
            "processes": len(proc_buckets),
            "metrics": len(metric_buckets),
        },
        "top_priorities": top_priorities,
        "pain_points": sorted(pain_buckets.values(), key=lambda b: (-b["priority_score"], -b["count"])),
        "opportunities": sorted(opp_buckets.values(), key=lambda b: (-b["priority_score"], -b["count"])),
        "tools": sorted(tool_buckets.values(), key=lambda b: (-b["count"], b["name"])),
        "processes": sorted(proc_buckets.values(), key=lambda b: (-b["count"], b["process_name"])),
        "metrics": sorted(metric_buckets.values(), key=lambda b: (-b["count"], b["name"])),
    }

        
    return out
