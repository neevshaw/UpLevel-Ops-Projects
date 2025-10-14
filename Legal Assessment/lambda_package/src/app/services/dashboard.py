from __future__ import annotations
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

from datetime import datetime
import time


def _read_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def render_dashboard(cs, pol, rec_data, syn, title: Optional[str] = None) -> Path:
    """
    Reads working/{job_id}/current_state.json (+ synthesis.json if present)
    and writes outputs/{job_id}/dashboard.html.
    """

    # Try to read policy-adjusted levels
    policy_by_id = {}
    policy_applied_count = 0
    if pol != None:
      for c in pol.get("categories", []):
          # Map by stable id; fall back to name if needed
          key = c.get("id") or c.get("name")
          policy_by_id[key] = c

    # Try to read recommendations
    recommendations = []
    if rec_data != None:
        recommendations = rec_data.get("recommendations", [])

    # Apply policy final levels if present
    for c in cs.get("categories", []):
        key = c.get("id") or c.get("name")
        pol = policy_by_id.get(key)
        if pol:
            original_level = c.get("level", 1)
            new_level = int(pol.get("final_level", pol.get("policy_level", original_level)))

            # Only mark as policy applied if level actually changed
            if new_level != original_level:
                c["original_level"] = original_level
                c["level"] = new_level
                c["policy_applied"] = True
                c["policy_confidence"] = pol.get("policy_confidence", None)
                policy_applied_count += 1

    syn = syn if syn!=None else {"top_priorities": [], "counts": {}}

    categories: List[Dict[str, Any]] = cs.get("categories", [])
    # Sort categories: lowest level first to highlight gaps
    categories_sorted = sorted(categories, key=lambda c: (c.get("level", 0), -c.get("confidence", 0)))

    page_title = title or "Legal Ops Current State"
    data_blob = {
        "categories": categories_sorted,
        "recommendations": recommendations[:10],  # Top 10 actionable recommendations
        "synthesis_counts": syn.get("counts", {}),
        "policy_applied_count": policy_applied_count,
    }

    from datetime import datetime
    import time

    build_tag = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cache_bust = int(time.time())

    html = f"""<!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8"/>
      <meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate, max-age=0"/>
      <meta http-equiv="Pragma" content="no-cache"/>
      <meta http-equiv="Expires" content="0"/>
      <meta name="viewport" content="width=device-width,initial-scale=1"/>
      <title>{page_title}</title>

      <link rel="preconnect" href="https://cdn.jsdelivr.net"/>
      <link rel="dns-prefetch" href="https://cdn.jsdelivr.net"/>
      <style>
        :root {{
          --bg:#1f262b; --card:#070e12; --muted:#94a3b8; --text:#e5e7eb; --accent:#38bdf8; --ok:#22c55e; --warn:#f59e0b; --bad:#ef4444; --policy:#a855f7;
        }}
        body {{ margin:0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Inter, Arial; background:var(--bg); color:var(--text); }}
        .wrap {{ max-width:1100px; margin:32px auto; padding:0 16px; }}
        .header {{ display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:24px; }}
        .title {{ font-size:24px; font-weight:700; }}
        .card {{ background:var(--card); border-radius:16px; padding:16px; box-shadow:0 6px 24px rgba(0,0,0,.25); }}
        .grid {{ display:grid; grid-template-columns: 1fr; gap:16px; }}
        @media (min-width: 900px) {{ .grid {{ grid-template-columns: 1.1fr .9fr; }} }}

        table {{ width:100%; border-collapse: collapse; margin-top:8px; }}
        th, td {{ padding:10px 12px; border-bottom:1px solid #1f2937; text-align:left; font-size:14px; }}
        th {{ color:#cbd5e1; font-weight:600; }}
        .pill {{ display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px; font-weight:700; }}
        .lvl-1 {{ background:rgba(239,68,68,.15); color:var(--bad); }}
        .lvl-2 {{ background:rgba(245,158,11,.15); color:var(--warn); }}
        .lvl-3 {{ background:rgba(56,189,248,.15); color:var(--accent); }}
        .lvl-4 {{ background:rgba(34,197,94,.15); color:var(--ok); }}
        .policy-badge {{ background:rgba(168,85,247,.15); color:var(--policy); border:1px solid rgba(168,85,247,.3); }}
        .policy-notice {{ background:rgba(168,85,247,.1); border-left:4px solid var(--policy); padding:12px; margin-bottom:16px; border-radius:4px; }}
        .recommendation {{ border-left:4px solid var(--accent); padding:16px; margin-bottom:12px; background:rgba(56,189,248,.05); border-radius:6px; }}
        .rec-header {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px; }}
        .rec-title {{ font-weight:600; font-size:14px; margin:0; }}
        .rec-meta {{ display:flex; gap:8px; }}
        .rec-badge {{ padding:2px 8px; border-radius:12px; font-size:11px; font-weight:600; }}
        .impact-high {{ background:rgba(34,197,94,.15); color:var(--ok); }}
        .impact-medium {{ background:rgba(56,189,248,.15); color:var(--accent); }}
        .impact-low {{ background:rgba(148,163,184,.15); color:var(--muted); }}
        .effort-high {{ background:rgba(239,68,68,.15); color:var(--bad); }}
        .effort-medium {{ background:rgba(245,158,11,.15); color:var(--warn); }}
        .effort-low {{ background:rgba(34,197,94,.15); color:var(--ok); }}
        .rec-description {{ font-size:13px; line-height:1.5; color:var(--muted); }}
        .muted {{ color: var(--muted); }}
        .policy-adjusted {{ border-left: 3px solid var(--policy); }}
        details summary {{ cursor:pointer; }}
        .small {{ font-size:12px; }}
        .section-title {{ font-size:18px; font-weight:700; margin:0 0 12px; }}

        /* Taller container to fit many horizontal bars */
        .chart-container {{
          position: relative;
          width: 100%;
          min-height: 820px; /* 19 bars * ~40px + padding */
        }}
        .logout-btn {{
          background: var(--bad);
          color: white;
          border: none;
          padding: 8px 16px;
          border-radius: 8px;
          font-weight: 600;
          cursor: pointer;
          transition: background 0.2s;
        }}
        .logout-btn:hover {{
          background: #dc2626; /* slightly darker red */
        }}
      </style>
    </head>
    <body>
    <div class="wrap">
      <div class="header">
        <div class="title">{page_title}</div>
        <a href="logout"><button class="logout-btn">Logout</button></a>
      </div>

      <!-- BUILD:{build_tag} -->

      <div id="policyNotice"></div>

      <div class="grid">
        <div class="card">
          <div class="section-title">Current State at a Glance</div>
          <div class="chart-container">
            <canvas id="barLevels"></canvas>
          </div>
          <div class="small muted" style="margin-top:8px;">
            Levels scale from 1 (Ad-hoc) to 4 (Strategic). Sorted by level ascending to highlight gaps.
            <span id="chartPolicyNote"></span>
          </div>
        </div>

        <div class="card">
          <div class="section-title">Top Recommendations</div>
          <div id="recommendationsList"></div>
          <div class="small muted" id="recommendationsEmpty" style="display:none;">No recommendations generated yet—run /pipeline/recommendations.</div>
        </div>
      </div>

      <div class="card" style="margin-top:16px;">
        <div class="section-title">Category Details</div>
        <table id="catTable">
          <thead>
            <tr>
              <th>Category</th>
              <th>Level</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>

    <script>
      console.log("DASHBOARD BUILD:", "{build_tag}");
    </script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.0/dist/chart.umd.min.js?v={cache_bust}"></script>
    <script>
    const DATA = {json.dumps(data_blob, ensure_ascii=False)};

    function levelClass(l) {{
      if (l >= 4) return "lvl-4";
      if (l >= 3) return "lvl-3";
      if (l >= 2) return "lvl-2";
      return "lvl-1";
    }}

    // Show policy notice if adjustments were made
    (function showPolicyNotice() {{
      if (DATA.policy_applied_count > 0) {{
        const notice = document.getElementById('policyNotice');
        notice.innerHTML = `
          <div class="policy-notice">
            <strong>📋 Policy Adjustments Applied</strong><br>
            <span class="small">${{DATA.policy_applied_count}} categories have been adjusted based on policy review. 
            Look for purple indicators in the table below.</span>
          </div>
        `;

        const chartNote = document.getElementById('chartPolicyNote');
        chartNote.innerHTML = ` Purple bars indicate policy-adjusted levels.`;
      }}
    }})();

    (function renderChart() {{
      function wrapLabel(s, max = 25) {{
        if (!s) return "";
        const words = String(s).split(/\\s+/);
        const lines = [];
        let line = "";
        for (const w of words) {{
          if ((line + " " + w).trim().length > max) {{
            if (line) lines.push(line.trim());
            line = w;
          }} else {{
            line = (line ? line + " " : "") + w;
          }}
        }}
        if (line) lines.push(line.trim());
        return lines;
      }}

      // Sort categories by level ascending to highlight gaps
      const sortedCategories = [...DATA.categories].sort((a, b) => a.level - b.level);

      const labelsRaw = sortedCategories.map(c => c.name || c.id);
      const labels = labelsRaw.map(l => wrapLabel(l, 25));
      const levels = sortedCategories.map(c => c.level);

      const canvas = document.getElementById('barLevels');
      const ctx = canvas.getContext('2d');

      // Dynamic height: ~40px per bar + padding
      const barHeight = 40;
      const padding = 140;
      const calculatedHeight = Math.max(600, labels.length * barHeight + padding);
      canvas.parentElement.style.height = calculatedHeight + 'px';

      const cfg = {{
        type: 'bar',
        data: {{
          labels: labels,
          datasets: [{{
            label: 'Level (1–4)',
            data: levels,
            backgroundColor: sortedCategories.map((cat, i) => {{
              const level = levels[i];
              const isPolicyAdjusted = cat.policy_applied;

              if (isPolicyAdjusted) return '#a855f7'; // Purple for policy-adjusted
              if (level >= 4) return '#22c55e';
              if (level >= 3) return '#38bdf8';
              if (level >= 2) return '#f59e0b';
              return '#ef4444';
            }}),
            borderColor: sortedCategories.map((cat, i) => {{
              const level = levels[i];
              const isPolicyAdjusted = cat.policy_applied;

              if (isPolicyAdjusted) return '#9333ea'; // Darker purple border
              if (level >= 4) return '#16a34a';
              if (level >= 3) return '#0284c7';
              if (level >= 2) return '#d97706';
              return '#dc2626';
            }}),
            borderWidth: 1,
            borderRadius: 4,
            borderSkipped: false,
          }}]
        }},
        options: {{
          indexAxis: 'y', // horizontal bars
          maintainAspectRatio: false,
          responsive: true,
          layout: {{
            padding: {{ left: 20, right: 20, top: 20, bottom: 20 }}
          }},
          scales: {{
            x: {{
              min: 0,
              max: 4,
              ticks: {{
                stepSize: 0.5,
                color: '#94a3b8',
                font: {{ size: 12 }}
              }},
              grid: {{ color: '#1f2937' }},
              title: {{
                display: true,
                text: 'Maturity Level',
                color: '#e5e7eb',
                font: {{ size: 14, weight: 'bold' }}
              }}
            }},
            y: {{
              ticks: {{
                autoSkip: false, // show all labels
                color: '#e5e7eb',
                font: {{ size: 12 }},
                maxRotation: 0,
                padding: 8
              }},
              grid: {{ display: false }}
            }}
          }},
          plugins: {{
            legend: {{ display: false }},
            tooltip: {{
              backgroundColor: '#111827',
              titleColor: '#e5e7eb',
              bodyColor: '#e5e7eb',
              borderColor: '#374151',
              borderWidth: 1,
              callbacks: {{
                // Safe join in case label is already a string
                title: (ctx) => Array.isArray(ctx?.[0]?.label) ? ctx[0].label.join(' ') : String(ctx?.[0]?.label ?? ''),
                label: (ctx) => {{
                  const x = ctx.parsed?.x;
                  const categoryIndex = ctx.dataIndex;
                  const category = sortedCategories[categoryIndex];
                  let result = 'Level: ' + (x?.toFixed ? x.toFixed(1) : x);

                  if (category.policy_applied) {{
                    result += ` (Policy Adjusted from Level ${{category.original_level}})`;
                    if (category.policy_confidence) {{
                      result += ` • Confidence: ${{Math.round(category.policy_confidence * 100)}}%`;
                    }}
                  }}
                  return result;
                }}
              }}
            }}
          }},
          animation: {{
            duration: 800,
            easing: 'easeOutQuart'
          }}
        }}
      }};

      console.log('Chart.js version:', Chart.version, '| categories:', labels.length, '| container height:', calculatedHeight);
      new Chart(ctx, cfg);
    }})();

    (function renderRecommendations() {{
      const container = document.getElementById('recommendationsList');
      const empty = document.getElementById('recommendationsEmpty');
      const items = DATA.recommendations || [];

      if (!items.length) {{
        empty.style.display = 'block';
        return;
      }}

      items.forEach((rec, i) => {{
        const div = document.createElement('div');
        div.className = 'recommendation';

        div.innerHTML = `
          <div class="rec-header">
            <h4 class="rec-title">${{rec.sequence}}. ${{rec.title}}</h4>
            <div class="rec-meta">
              <span class="rec-badge impact-${{rec.impact}}">Impact: ${{rec.impact}}</span>
              <span class="rec-badge effort-${{rec.effort}}">Effort: ${{rec.effort}}</span>
              <span class="rec-badge" style="background:rgba(148,163,184,.15); color:var(--muted);">Score: ${{rec.priority_score}}</span>
            </div>
          </div>
          <div class="rec-description">${{rec.description}}</div>
          <div class="small muted" style="margin-top:8px;">
            Category: ${{rec.category}} • Timeline: ${{rec.timeline}}
            ${{rec.prerequisites.length ? ' • Prerequisites: ' + rec.prerequisites.join(', ') : ''}}
          </div>
        `;

        container.appendChild(div);
      }});
    }})();

    (function renderTable() {{
      const tb = document.querySelector('#catTable tbody');
      DATA.categories.forEach(c => {{
        const tr = document.createElement('tr');
        if (c.policy_applied) {{
          tr.className = 'policy-adjusted';
        }}

        const tdName = document.createElement('td');
        tdName.textContent = c.name || c.id;
        tr.appendChild(tdName);

        const tdLvl = document.createElement('td');
        const span = document.createElement('span');
        span.className = `pill ${{levelClass(c.level)}}`;
        span.textContent = `Level ${{c.level}}`;
        tdLvl.appendChild(span);

        // Add policy indicator
        if (c.policy_applied) {{
          const policySpan = document.createElement('span');
          policySpan.className = 'pill policy-badge small';
          policySpan.textContent = `Policy (was L${{c.original_level}})`;
          policySpan.style.marginLeft = '8px';
          tdLvl.appendChild(policySpan);
        }}
        tr.appendChild(tdLvl);


        const tdEv = document.createElement('td');
        const det = document.createElement('details');
        const sum = document.createElement('summary');
        sum.textContent = 'View';
        det.appendChild(sum);

        (c.criteria || []).slice(0, 2).forEach(cr => {{
          const div = document.createElement('div');
          div.className = 'small muted';
          const ev = (cr.evidence || []).map(e => {{
            const s = e.source || {{}};
            const parts = [s.file, s.locator].filter(Boolean).join('#');
            return parts || '(source)';
          }}).slice(0,3).join(' • ');
          div.textContent = `${{cr.label || cr.id}} → L${{cr.level}}  —  ${{ev}}`;
          det.appendChild(div);
        }});
        tdEv.appendChild(det);
        tr.appendChild(tdEv);

        tb.appendChild(tr);
      }});
    }})();
    </script>
    </body>
    </html>"""

    return html