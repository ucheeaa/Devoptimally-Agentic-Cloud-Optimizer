"""
Cloud Optimizer Agent — powered by Strands Agents SDK + Amazon Bedrock
"""

import json
import os
from typing import Callable

from strands import Agent
from strands.models import BedrockModel

from agent.prompts import SYSTEM_PROMPT
from tools.cost_tool import analyze_costs
from tools.metrics_tool import get_metrics
from tools.architecture_tool import analyze_architecture

DEFAULT_ENV_FILE = "data/sample_environment.json"
DEFAULT_MODEL = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
DEFAULT_REGION = os.getenv("AWS_REGION", "us-east-1")


def build_agent(callback_handler=None) -> Agent:
    """Construct a Strands Agent wired to Bedrock and the three optimizer tools."""
    model = BedrockModel(
        model_id=DEFAULT_MODEL,
        region_name=DEFAULT_REGION,
        temperature=0.3,
    )

    kwargs = dict(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[analyze_costs, get_metrics, analyze_architecture],
    )
    if callback_handler is not None:
        kwargs["callback_handler"] = callback_handler

    return Agent(**kwargs)


class CloudOptimizerAgent:
    """
    Thin wrapper around a Strands Agent that:
    - Runs the agentic loop for a given task
    - Optionally streams tool-call events via an on_tool_call callback
    """

    def __init__(
        self,
        env_file: str = DEFAULT_ENV_FILE,
        on_tool_call: Callable[[str], None] | None = None,
    ):
        self.env_file = env_file
        self.tool_calls: list[str] = []
        self._on_tool_call = on_tool_call

        # Build a callback handler that tracks tool usage
        tool_calls_ref = self.tool_calls
        on_tool_call_ref = on_tool_call

        def callback_handler(**kwargs):
            if "current_tool_use" in kwargs:
                tool = kwargs["current_tool_use"]
                name = tool.get("name")
                if name and (not tool_calls_ref or tool_calls_ref[-1] != name):
                    tool_calls_ref.append(name)
                    if on_tool_call_ref:
                        on_tool_call_ref(name)

        self._agent = build_agent(callback_handler=callback_handler)

    def run(self, task: str) -> dict:
        """
        Run the agent on the given task.

        Returns a dict with:
          - raw_response: full text from the agent
          - tool_calls: list of tool names that were invoked
        """
        self.tool_calls = []

        # Inject the environment file path into the task so the agent
        # passes it through to the tools automatically
        full_task = (
            f"{task}\n\n"
            f"Use environment file: {self.env_file}"
        )

        result = self._agent(full_task)
        return {
            "raw_response": str(result),
            "tool_calls": self.tool_calls,
        }
