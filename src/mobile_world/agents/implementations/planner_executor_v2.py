"""Planner-executor with clearer scroll semantics and a progress ledger."""

import re
from typing import Any

from loguru import logger

from mobile_world.agents.implementations.planner_executor import PlannerExecutorAgentMCP
from mobile_world.agents.utils.prompts import PLANNER_EXECUTOR_V2_PROMPT_TEMPLATE
from mobile_world.runtime.utils.models import JSONAction

PROGRESS_PATTERN = re.compile(r"Progress:\s*(.*?)\s*Action:", re.S)

FINISH_CHECK_NOTE = (
    "You tried to end the task, but it has NOT been ended yet. Before ending, compare the user "
    "goal with your Progress notes item by item, and make sure every required item is actually "
    "done (including items you may not have seen yet). If everything is done, repeat your final "
    "action; otherwise continue working."
)


class PlannerExecutorV2AgentMCP(PlannerExecutorAgentMCP):
    prompt_template = PLANNER_EXECUTOR_V2_PROMPT_TEMPLATE

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reset_v2_state()

    def _reset_v2_state(self) -> None:
        self._finish_checked = False
        self._pending_notes: list[str] = []

    def reset(self):
        super().reset()
        self._reset_v2_state()

    def _latest_progress(self) -> str | None:
        if not self.plans:
            return None
        match = PROGRESS_PATTERN.search(self.plans[-1])
        return match.group(1).strip() if match else None

    def _observation_feedback(self, observation: dict[str, Any]) -> str | None:
        notes = self._pending_notes
        self._pending_notes = []

        sections = []
        progress = self._latest_progress()
        if progress:
            sections.append(f"[Your Progress notes from the previous step]\n{progress}")
        if notes:
            sections.append("[Harness notes]\n" + "\n".join(f"- {note}" for note in notes))
        if not sections:
            return None
        feedback = "\n\n".join(sections)
        logger.info(f"Observation feedback:\n{feedback}")
        return feedback

    def predict(self, observation: dict[str, Any]) -> tuple[str, JSONAction]:
        plan, action = super().predict(observation)
        if action.action_type == "answer" and not self._finish_checked:
            self._finish_checked = True
            self._pending_notes.append(FINISH_CHECK_NOTE)
            self.actions[-1] = {"action_type": "wait"}
            logger.info(f"Deferring first attempt to end the task: {action}")
            return plan, JSONAction(action_type="wait")
        return plan, action
