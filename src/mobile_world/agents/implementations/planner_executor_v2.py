"""Planner-executor with clearer scroll semantics, a progress ledger, and loop feedback."""

import re
from typing import Any

from loguru import logger
from PIL import Image, ImageChops, ImageStat

from mobile_world.agents.implementations.planner_executor import PlannerExecutorAgentMCP
from mobile_world.agents.utils.prompts import PLANNER_EXECUTOR_V2_PROMPT_TEMPLATE
from mobile_world.runtime.utils.models import JSONAction

# Mean per-pixel grayscale difference (0-255) below which two screens count as identical.
# Calibrated on emulator screenshots: a scroll that hits the end of a list gives 0.00,
# typing into a field gives >= 0.14, a regular scroll ~8.
NO_CHANGE_THRESHOLD = 0.02
# The status bar clock changes between screenshots, so it is excluded from the comparison.
STATUS_BAR_FRACTION = 0.05

SCROLL_WINDOW = 8
SCROLL_WINDOW_LIMIT = 6
REPEAT_LIMIT = 3

ACTIONS_WITHOUT_SCREEN_EFFECT = {"wait", "answer", "unknown", "mcp", "ask_user"}

PROGRESS_PATTERN = re.compile(r"Progress:\s*(.*?)\s*Action:", re.S)

FINISH_CHECK_NOTE = (
    "You tried to end the task, but it has NOT been ended yet. Before ending, compare the user "
    "goal with your Progress notes item by item, and make sure every required item is actually "
    "done (including items you may not have seen yet). If everything is done, repeat your final "
    "action; otherwise continue working."
)


def _screen_signature(image: Image.Image) -> Image.Image:
    gray = image.convert("L")
    width, height = gray.size
    return gray.crop((0, int(height * STATUS_BAR_FRACTION), width, height)).resize((135, 285))


def _screen_changed(previous: Image.Image, current: Image.Image) -> bool:
    diff = ImageChops.difference(_screen_signature(previous), _screen_signature(current))
    return ImageStat.Stat(diff).mean[0] > NO_CHANGE_THRESHOLD


class PlannerExecutorV2AgentMCP(PlannerExecutorAgentMCP):
    prompt_template = PLANNER_EXECUTOR_V2_PROMPT_TEMPLATE

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reset_v2_state()

    def _reset_v2_state(self) -> None:
        self._previous_screenshot = None
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

    def _screen_notes(self, screenshot: Image.Image | None) -> list[str]:
        if not self.actions or self._previous_screenshot is None or screenshot is None:
            return []
        last = self.actions[-1]
        action_type = last.get("action_type")
        if action_type in ACTIONS_WITHOUT_SCREEN_EFFECT:
            return []
        if _screen_changed(self._previous_screenshot, screenshot):
            return []
        if action_type == "scroll":
            return [
                f"Your last action (scroll {last.get('direction')}) did not change the screen: "
                "there is no more content in that direction."
            ]
        return [
            f"The screen did not change after your last action ({action_type}). It may have "
            "missed its target; do not repeat it unchanged."
        ]

    def _repetition_notes(self) -> list[str]:
        notes = []
        recent = self.actions[-SCROLL_WINDOW:]
        scroll_count = sum(1 for a in recent if a.get("action_type") == "scroll")
        if (
            recent
            and recent[-1].get("action_type") == "scroll"
            and scroll_count >= SCROLL_WINDOW_LIMIT
        ):
            notes.append(
                f"{scroll_count} of your last {len(recent)} actions were scrolls. Rely on your "
                "Progress notes instead of re-checking content you already recorded. If you "
                "still need to find items, use the app's search, sort, or filter options."
            )

        repeats = 0
        for action in reversed(self.actions):
            if action != self.actions[-1]:
                break
            repeats += 1
        if repeats >= REPEAT_LIMIT and self.actions[-1].get("action_type") != "scroll":
            notes.append(
                f"You have repeated the same action {repeats} times in a row. Try a different "
                "approach."
            )
        return notes

    def _observation_feedback(self, observation: dict[str, Any]) -> str | None:
        screenshot = observation.get("screenshot")
        notes = self._pending_notes + self._screen_notes(screenshot) + self._repetition_notes()
        self._pending_notes = []
        self._previous_screenshot = screenshot

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
