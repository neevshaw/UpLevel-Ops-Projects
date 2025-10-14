from __future__ import annotations
import json, os
from pathlib import Path
from typing import Dict, List, Any, Optional

from ..services.maturity import load_maturity_model

# OpenAI client - required for this module
try:
    from openai import OpenAI
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY environment variable is required")
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    print("Using LLM for recommendations")
except Exception as e:
    raise RuntimeError(f"OpenAI client initialization failed: {e}")

MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")




def _build_analysis_prompt(current_state: Dict[str, Any], synthesis: Dict[str, Any], maturity_model: Dict[str, Any]) -> \
List[Dict[str, str]]:
    """Build the prompt for LLM to generate recommendations"""

    # Summarize current maturity levels
    categories_summary = []
    for cat in current_state.get("categories", []):
        level = cat.get("level", 1)
        confidence = cat.get("confidence", 0)
        coverage = cat.get("coverage", 0)
        name = cat.get("name", cat.get("id", ""))

        status = "Strong" if level >= 3 and confidence >= 0.7 else "Needs Attention"
        categories_summary.append(
            f"- {name}: Level {level} ({status}, {int(confidence * 100)}% confidence, {int(coverage * 100)}% coverage)")

    # Summarize top pain points
    pain_summary = []
    for pain in synthesis.get("pain_points", [])[:5]:
        pain_summary.append(f"- {pain.get('text', '')} (mentioned {pain.get('count', 1)}x)")

    # Summarize top opportunities
    opp_summary = []
    for opp in synthesis.get("opportunities", [])[:5]:
        opp_summary.append(f"- {opp.get('description', '')} (mentioned {opp.get('count', 1)}x)")

    # Extract maturity model definitions for context
    model_context = []
    for cat in maturity_model.get("categories", [])[:10]:  # limit to keep prompt manageable
        model_context.append(f"**{cat.get('name', '')}**: Levels 1-4 represent progression from ad-hoc to strategic")

    system_prompt = """You are a legal operations consultant specializing in generating actionable recommendations based on maturity assessments. 

Your task is to analyze the current state assessment, pain points, and opportunities to generate 8-10 specific, actionable recommendations that will have the highest impact on improving legal operations maturity.

Requirements:
- Each recommendation must be specific and actionable (not vague)
- Focus on addressing the lowest maturity areas first
- Consider pain points and opportunities as context
- Recommendations should build logically (some may have prerequisites)
- Include timeline estimates and effort/impact ratings
- Return ONLY valid JSON matching the schema below

JSON Schema:
{
  "recommendations": [
    {
      "sequence": 1,
      "title": "Short Action-Oriented Title",
      "description": "Detailed description explaining what to do and why it matters. Should be 2-3 sentences.",
      "category": "Which Legal Ops category this addresses",
      "impact": "high|medium|low",
      "effort": "high|medium|low", 
      "timeline": "immediate|short-term|medium-term|long-term",
      "prerequisites": ["list", "of", "other", "recommendation", "titles", "if", "any"],
      "priority_score": 1-10,
      "addresses_gaps": ["specific", "maturity", "gaps", "this", "fixes"]
    }
  ]
}"""

    user_prompt = f"""CURRENT MATURITY ASSESSMENT:
{chr(10).join(categories_summary)}

TOP PAIN POINTS IDENTIFIED:
{chr(10).join(pain_summary) if pain_summary else "None identified"}

TOP OPPORTUNITIES IDENTIFIED:
{chr(10).join(opp_summary) if opp_summary else "None identified"}

MATURITY MODEL CONTEXT:
{chr(10).join(model_context)}

Based on this analysis, generate 8-10 actionable recommendations that will most effectively improve legal operations maturity. Focus on addressing the lowest-scoring categories and biggest pain points first. Each recommendation should be specific enough that a legal operations professional could immediately begin implementation.

Prioritize recommendations that:
1. Address categories with Level 1-2 maturity
2. Solve specific pain points mentioned in the assessment  
3. Build foundational capabilities that enable future improvements
4. Have clear success metrics and outcomes

Return only the JSON response."""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]


def generate_recommendations(synthesis, current_state, max_recommendations: int = 5) -> Path:
    """
    Generate actionable recommendations based on current state and synthesis data.
    Uses LLM to generate recommendations.
    Writes working/{job_id}/recommendations.json
    """

    # Load required data

    # Load maturity model for context
    try:
        model, raw_model = load_maturity_model()
        maturity_defs = raw_model
    except Exception:
        maturity_defs = {"categories": []}

    # Generate recommendations using LLM
    try:
        messages = _build_analysis_prompt(current_state, synthesis, maturity_defs)

        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.3,  # slight creativity for varied recommendations
            response_format={"type": "json_object"}
        )

        llm_output = json.loads(resp.choices[0].message.content)
        recommendations = llm_output.get("recommendations", [])

        # Validate and clean up LLM output
        for i, rec in enumerate(recommendations):
            rec["sequence"] = i + 1
            rec["priority_score"] = int(rec.get("priority_score", 5))
            rec["prerequisites"] = rec.get("prerequisites", [])
            rec["addresses_gaps"] = rec.get("addresses_gaps", [])

        print(f"Generated {len(recommendations)} recommendations using LLM")

    except Exception as e:
        raise RuntimeError(f"LLM recommendation generation failed: {e}")

    # Limit to requested number
    recommendations = recommendations[:max_recommendations]

    # Build output structure
    output = {
        "generation_method": "llm",
        "data_source": current_state.get("data_source", "unknown"),
        "total_categories": len(current_state.get("categories", [])),
        "low_maturity_categories": len([c for c in current_state.get("categories", []) if c.get("level", 1) <= 2]),
        "recommendations_count": len(recommendations),
        "recommendations": recommendations,
        "synthesis_context": {
            "pain_points_count": len(synthesis.get("pain_points", [])),
            "opportunities_count": len(synthesis.get("opportunities", [])),
            "tools_count": synthesis.get("counts", {}).get("tools", 0)
        }
    }

    # Write output file
    return output