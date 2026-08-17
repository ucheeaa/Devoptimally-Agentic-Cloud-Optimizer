"""
DevOptimally - Agentic Cloud Optimization UI
"""

import json
import re
import time

import streamlit as st

st.set_page_config(
    page_title="DevOptimally",
    page_icon="☁️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #0d1117;
    color: #e6edf3;
}
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem; max-width: 740px; }

.card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1rem;
}
.card-accent { border-color: #388bfd; }

.app-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.2rem;
}
.app-title   { font-size: 1.4rem; font-weight: 700; color: #e6edf3; margin: 0; }
.app-subtitle { font-size: 0.82rem; color: #8b949e; margin: 0; }
.powered-by  { font-size: 0.72rem; color: #388bfd; margin-top: 0.15rem; }

.badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    white-space: nowrap;
}
.badge-green  { background:#1a3a2a; color:#3fb950; border:1px solid #2ea043; }
.badge-yellow { background:#3a2e1a; color:#d29922; border:1px solid #9e6a03; }
.badge-red    { background:#3a1a1a; color:#f85149; border:1px solid #b91c1c; }
.badge-blue   { background:#1a2a3a; color:#58a6ff; border:1px solid #1f6feb; }
.badge-gray   { background:#21262d; color:#8b949e; border:1px solid #30363d; }

.metric-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0;
    border-bottom: 1px solid #21262d;
    font-size: 0.9rem;
}
.metric-row:last-child { border-bottom: none; }
.metric-label { color: #8b949e; }
.metric-value { color: #e6edf3; font-weight: 600; }

.section-label {
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    color: #8b949e;
    text-transform: uppercase;
    margin-bottom: 0.9rem;
}

.step {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-size: 0.88rem;
    padding: 0.3rem 0;
}
.step-done    { color: #3fb950; }
.step-pending { color: #30363d; }
.step-icon    { font-size: 0.9rem; width: 1.2rem; text-align: center; }

.rec-title { font-size: 1.05rem; font-weight: 700; color: #e6edf3; margin-bottom: 1rem; }
.rec-meta  { display: flex; gap: 2.5rem; margin-bottom: 1rem; }
.rec-meta-item { display: flex; flex-direction: column; gap: 4px; }
.rec-meta-label { font-size: 0.65rem; color: #8b949e; text-transform: uppercase; letter-spacing: 0.08em; }
.rec-meta-value { font-size: 1rem; font-weight: 700; }
.rec-body { font-size: 0.88rem; color: #c9d1d9; line-height: 1.65; }

.data-source-pill {
    display: inline-block;
    background: #1a2a3a;
    border: 1px solid #1f6feb;
    color: #58a6ff;
    font-size: 0.68rem;
    padding: 2px 8px;
    border-radius: 20px;
    margin-bottom: 0.8rem;
}

.stTextArea textarea {
    background: #0d1117 !important;
    border: 1px solid #30363d !important;
    border-radius: 8px !important;
    color: #e6edf3 !important;
    font-size: 0.9rem !important;
    font-family: 'Inter', sans-serif !important;
    resize: none !important;
}
.stTextArea textarea:focus {
    border-color: #388bfd !important;
    box-shadow: 0 0 0 3px rgba(56,139,253,0.12) !important;
}
.stButton > button {
    background: linear-gradient(135deg, #238636, #2ea043) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    width: 100% !important;
    padding: 0.6rem !important;
    transition: opacity 0.15s !important;
}
.stButton > button:hover { opacity: 0.88 !important; }
.stButton > button:disabled { background: #21262d !important; color: #484f58 !important; }

.stSpinner > div { border-top-color: #388bfd !important; }

details summary {
    background: #21262d !important;
    border-radius: 6px !important;
    font-size: 0.82rem !important;
    color: #8b949e !important;
    padding: 0.4rem 0.8rem !important;
}

.suggestion-pill {
    display: inline-block;
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 0.78rem;
    color: #8b949e;
    cursor: pointer;
    margin: 0 4px 4px 0;
    transition: all 0.15s;
}
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
TOOL_LABELS = {
    "analyze_architecture": "Inspected architecture",
    "get_metrics":          "Retrieved utilization metrics",
    "analyze_costs":        "Analyzed cost breakdown",
}
ALL_STEPS = [
    "Inspected architecture",
    "Retrieved utilization metrics",
    "Analyzed cost breakdown",
    "Evaluated optimization options",
]
SUGGESTIONS = [
    "Find the safest way to reduce our cloud cost.",
    "Which resources are over-provisioned?",
    "What are our biggest architecture risks?",
    "How can we improve compute utilization?",
]

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in [("result", None), ("steps_done", []), ("error", None), ("task", SUGGESTIONS[0])]:
    if k not in st.session_state:
        st.session_state[k] = v


# ── Helpers ───────────────────────────────────────────────────────────────────
def parse_response(raw: str) -> dict | None:
    for attempt in [
        lambda: json.loads(raw.strip()),
        lambda: json.loads(re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()),
        lambda: json.loads(re.search(r"\{.*\}", raw, re.DOTALL).group()),
    ]:
        try:
            return attempt()
        except Exception:
            pass
    return None


def run_agent(task: str):
    from agent.agent import CloudOptimizerAgent
    steps: list[str] = []

    def on_tool_call(name: str):
        label = TOOL_LABELS.get(name, name)
        if label not in steps:
            steps.append(label)

    agent  = CloudOptimizerAgent(on_tool_call=on_tool_call)
    output = agent.run(task)
    if "Evaluated optimization options" not in steps:
        steps.append("Evaluated optimization options")
    return output, steps


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="card">
  <div class="app-header">
    <span style="font-size:1.6rem;">☁️</span>
    <div>
      <p class="app-title">DevOptimally</p>
      <p class="app-subtitle">Agentic Cloud Optimization</p>
    </div>
  </div>
  <p class="powered-by">⚡ Powered by Amazon Bedrock &nbsp;·&nbsp; Strands Agents SDK</p>
</div>
""", unsafe_allow_html=True)

# ── Environment summary ───────────────────────────────────────────────────────
summary = None
data_source = None
if st.session_state.result:
    parsed = parse_response(st.session_state.result.get("raw_response", ""))
    if parsed:
        summary     = parsed.get("summary")
        data_source = parsed.get("data_source")

env_name    = summary["environment"]               if summary else "Production"
total_cost  = f"${summary['total_monthly_cost_usd']:,.0f}" if summary else "—"
utilization = f"{summary['avg_compute_utilization_pct']}%"  if summary else "—"
arch        = summary.get("architecture_rating","—")        if summary else "—"

arch_class = (
    "badge-green"  if arch == "Resilient" else
    "badge-yellow" if arch == "Multi-AZ"  else
    "badge-red"    if arch == "Single-AZ" else "badge-gray"
)

ds_html = f'<span class="data-source-pill">🔴 Live AWS data</span>' if (
    data_source and "live" in data_source.lower()
) else f'<span class="data-source-pill">🟡 Sample data</span>' if data_source else ""

st.markdown(f"""
<div class="card">
  {ds_html}
  <div class="metric-row">
    <span class="metric-label">Environment</span>
    <span class="badge badge-green">● {env_name}</span>
  </div>
  <div class="metric-row">
    <span class="metric-label">Current Monthly Cost</span>
    <span class="metric-value">{total_cost}</span>
  </div>
  <div class="metric-row">
    <span class="metric-label">Compute Utilization</span>
    <span class="metric-value">{utilization}</span>
  </div>
  <div class="metric-row">
    <span class="metric-label">Architecture</span>
    <span class="badge {arch_class}">{arch}</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Ask panel ─────────────────────────────────────────────────────────────────
st.markdown('<div class="card card-accent">', unsafe_allow_html=True)
st.markdown('<div class="section-label">Ask DevOptimally</div>', unsafe_allow_html=True)

task = st.text_area(
    label="task",
    value=st.session_state.task,
    height=72,
    label_visibility="collapsed",
    key="task_input",
)

analyze_clicked = st.button("⚡  Analyze", key="analyze_btn")
st.markdown("</div>", unsafe_allow_html=True)

# Suggestion pills (click to populate)
cols = st.columns(len(SUGGESTIONS))
for i, (col, suggestion) in enumerate(zip(cols, SUGGESTIONS)):
    with col:
        if st.button(suggestion[:28] + "…", key=f"sug_{i}", help=suggestion):
            st.session_state.task = suggestion
            st.rerun()

# ── Agent execution ───────────────────────────────────────────────────────────
if analyze_clicked and task.strip():
    st.session_state.result     = None
    st.session_state.steps_done = []
    st.session_state.error      = None

    with st.spinner("Agent is investigating your environment…"):
        try:
            output, steps = run_agent(task.strip())
            st.session_state.result     = output
            st.session_state.steps_done = steps
        except Exception as exc:
            st.session_state.error = str(exc)
    st.rerun()

# ── Error ─────────────────────────────────────────────────────────────────────
if st.session_state.error:
    st.markdown(f"""
    <div class="card" style="border-color:#f85149;">
      <div class="section-label" style="color:#f85149;">Error</div>
      <p style="color:#f85149; font-size:0.88rem; margin:0 0 0.4rem;">{st.session_state.error}</p>
      <p style="color:#8b949e; font-size:0.78rem; margin:0;">
        Check that <code>aws login --region us-east-2</code> has been run and Bedrock access is enabled.
      </p>
    </div>
    """, unsafe_allow_html=True)

# ── Agent Investigation ───────────────────────────────────────────────────────
if st.session_state.steps_done:
    done_set   = set(st.session_state.steps_done)
    steps_html = ""
    for step in ALL_STEPS:
        if step in done_set:
            steps_html += f'<div class="step step-done"><span class="step-icon">✓</span>{step}</div>'
        else:
            steps_html += f'<div class="step step-pending"><span class="step-icon">○</span>{step}</div>'

    st.markdown(f"""
    <div class="card">
      <div class="section-label">Agent Investigation</div>
      {steps_html}
    </div>
    """, unsafe_allow_html=True)

# ── Recommendation ────────────────────────────────────────────────────────────
if st.session_state.result:
    raw    = st.session_state.result.get("raw_response", "")
    parsed = parse_response(raw)

    if parsed and "recommendation" in parsed:
        rec         = parsed["recommendation"]
        title       = rec.get("title", "Optimization Opportunity")
        savings     = rec.get("monthly_savings_usd", 0)
        risk        = rec.get("risk", "MEDIUM")
        explanation = rec.get("explanation", "")
        evidence    = rec.get("evidence", [])
        alternatives = rec.get("alternatives", [])

        risk_class  = (
            "badge-green"  if risk == "LOW"    else
            "badge-yellow" if risk == "MEDIUM" else "badge-red"
        )
        savings_color = "#3fb950" if savings > 0 else "#e6edf3"

        st.markdown(f"""
        <div class="card">
          <div class="section-label">Recommendation</div>
          <div class="rec-title">{title}</div>
          <div class="rec-meta">
            <div class="rec-meta-item">
              <span class="rec-meta-label">Monthly Saving</span>
              <span class="rec-meta-value" style="color:{savings_color};">${savings:,.0f}</span>
            </div>
            <div class="rec-meta-item">
              <span class="rec-meta-label">Risk</span>
              <span class="badge {risk_class}" style="margin-top:2px;">{risk}</span>
            </div>
          </div>
          <p class="rec-body">{explanation}</p>
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            with st.expander("Evidence"):
                if evidence:
                    for e in evidence:
                        st.markdown(f"- {e}")
                else:
                    st.caption("No evidence data.")
        with col2:
            with st.expander("Alternatives"):
                if alternatives:
                    for a in alternatives:
                        r = a.get("risk", "")
                        badge = "🟢" if r == "LOW" else "🟡" if r == "MEDIUM" else "🔴"
                        st.markdown(f"**{a.get('title','')}** {badge}")
                        st.caption(f"${a.get('monthly_savings_usd',0):,.0f}/mo · {a.get('note','')}")
                        st.divider()
                else:
                    st.caption("No alternatives.")
    else:
        # Raw fallback
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="section-label">Response</div>', unsafe_allow_html=True)
        st.markdown(
            f"<pre style='font-size:0.82rem;color:#c9d1d9;white-space:pre-wrap;'>{raw}</pre>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)
