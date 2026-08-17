"""
Devoptimally Agentic Cloud Optimizer
CLI entry point — for terminal usage without the Streamlit UI.
Run the UI with: streamlit run ui.py
"""

import os
import json
from dotenv import load_dotenv
from agent.agent import CloudOptimizerAgent

load_dotenv()


def main():
    print("=== Devoptimally Agentic Cloud Optimizer ===\n")

    def on_tool_call(name: str):
        labels = {
            "analyze_architecture": "Inspected architecture",
            "get_metrics": "Retrieved utilization",
            "analyze_costs": "Analyzed cost",
        }
        print(f"  ✓ {labels.get(name, name)}")

    agent = CloudOptimizerAgent(on_tool_call=on_tool_call)

    task = (
        "Find the safest way to reduce our cloud cost. "
        "Analyze costs, performance metrics, and architecture, "
        "then return a single prioritized recommendation."
    )

    print(f"Task: {task}\n")
    print("Agent running...\n")

    output = agent.run(task)
    raw = output.get("raw_response", "")

    print("\n=== Optimization Report ===\n")

    # Try to pretty-print as JSON
    try:
        parsed = json.loads(raw.strip())
        print(json.dumps(parsed, indent=2))
    except Exception:
        print(raw)


if __name__ == "__main__":
    main()
