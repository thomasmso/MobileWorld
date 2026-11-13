"""Planner-executor with clearer scroll semantics."""

from mobile_world.agents.implementations.planner_executor import PlannerExecutorAgentMCP
from mobile_world.agents.utils.prompts import PLANNER_EXECUTOR_V2_PROMPT_TEMPLATE


class PlannerExecutorV2AgentMCP(PlannerExecutorAgentMCP):
    prompt_template = PLANNER_EXECUTOR_V2_PROMPT_TEMPLATE
