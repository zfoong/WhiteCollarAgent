from datetime import datetime, timezone

from tzlocal import get_localzone
import json

from core.config import AGENT_WORKSPACE_ROOT
from core.gui.handler import GUIHandler
from core.logger import logger
from core.prompt import (
    AGENT_ROLE_PROMPT,
    AGENT_INFO_PROMPT,
    ENVIRONMENTAL_CONTEXT_PROMPT,
    POLICY_PROMPT,
)
from core.state.state_manager import StateManager
from core.state.agent_state import STATE
from typing import Optional, Dict, Any
from core.task.task import Task

"""
core.context_engine

The main context engine that constructs
system prompt and user prompt. System prompt for agent roles are overwrite
by specialise agent.

KV CACHING OPTIMIZATION:
- System prompts are now COMPLETELY STATIC (no dynamic content)
- All dynamic content (event_stream, task_state, agent_state) moved to user prompts
- This maximizes KV cache hit rate for LLM inference
"""

class ContextEngine:
    """Build structured prompts for the LLM from runtime state.

    The engine centralizes all context-building logic so callers can request a
    ready-to-send pair of system and user messages without worrying about where
    the information originates (conversation history, event stream, etc.).

    KV Caching Strategy:
    - System prompt: STATIC only (agent_info, policy, role_info, environment basics)
    - User prompt: Static template first, then dynamic content, then output format
    """

    def __init__(self, state_manager: StateManager, agent_identity="General AI Assistant"):
        """
        Initializes the ContextEngine with optional defaults for each prompt component.

        agent_identity:
            Default identity/persona string to include in the system prompt when
            no role-specific hook is provided.
        """
        self.agent_identity = agent_identity
        self.system_messages = []
        self.user_messages = []
        self._role_info_func = None  # injected by AgentBase or subclass
        self.state_manager = state_manager
        
    # ─────────────── SYSTEM MESSAGE COMPONENTS (STATIC ONLY) ───────────────
    # These components are STATIC and contribute to KV cache hits

    def create_system_agent_info(self):
        """
        Create a system message block describing the CraftOS, agent's identity and mechanism.
        STATIC - suitable for KV caching.
        """
        prompt = AGENT_INFO_PROMPT
        return prompt

    def set_role_info_hook(self, hook_fn):
        """
        Injects a role-specific system prompt generator.

        This should be a callable that returns a string.
        """
        self._role_info_func = hook_fn

    def create_system_role_info(self):
        """
        Calls the injected role-specific prompt function, if any.
        SEMI-STATIC - changes only when agent role changes (rare).
        """
        if self._role_info_func:
            role = self._role_info_func()
            return AGENT_ROLE_PROMPT.format(role=role)
        return ""

    def create_system_policy(self):
        """
        Create a system message block with constraints: safety, compliance, privacy, do/don't lists, etc.
        STATIC - suitable for KV caching.
        """
        prompt = POLICY_PROMPT
        return prompt

    def create_system_environmental_context(self):
        """
        Create a system message block with environmental context.
        STATIC version - no timestamp to maximize KV cache hits.
        """
        import platform
        local_timezone = get_localzone()
        prompt = ENVIRONMENTAL_CONTEXT_PROMPT.format(
            user_location=local_timezone,
            working_directory=AGENT_WORKSPACE_ROOT,
            operating_system=platform.system(),
            os_version=platform.release(),
            os_platform=platform.platform(),
            vm_operating_system="Linux",
            vm_os_version="6.12.13",
            vm_os_platform="Linux a5e39e32118c 6.12.13 #1 SMP Thu Mar 13 11:34:50 UTC 2025 x86_64 x86_64 x86_64 GNU/Linux",
            vm_resolution="1064 x 1064"
        )
        return prompt

    def create_system_base_instruction(self):
        """
        Create a system message of instruction.
        STATIC - suitable for KV caching.
        """
        return "Please assist the user using the context given in the conversation or event stream."

    # ─────────────── USER PROMPT DYNAMIC COMPONENTS ───────────────
    # These components are DYNAMIC and should be included in user prompts
    # They are placed AFTER static template content but BEFORE output format

    def get_event_stream(self) -> str:
        """
        Get the event stream content for inclusion in user prompts.
        """
        event_stream = STATE.event_stream
        if event_stream:
            return (
                "<event_stream>\n"
                "Use the event stream to understand the current situation and past agent actions:\n"
                f"{event_stream}\n"
                "</event_stream>"
            )
        return "<event_stream>\n(no events yet)\n</event_stream>"

    def get_event_stream_delta(self, call_type: str) -> tuple[str, bool]:
        """
        Get only new events since the last session sync for session caching.

        For BytePlus session caching, we only want to send new events
        instead of the full event stream on subsequent calls.

        Args:
            call_type: The type of LLM call (e.g., "action_selection")

        Returns:
            Tuple of (delta_events_wrapped, has_delta).
            - delta_events_wrapped: The new events wrapped in event_stream tags, or empty string
            - has_delta: True if there are new events to send
        """
        from core.event_stream.event_stream_manager import EventStreamManager

        event_stream_manager: EventStreamManager = self.state_manager.event_stream_manager
        stream = event_stream_manager.get_stream()

        if not stream:
            return "", False

        delta_str, has_delta = stream.get_delta_events(call_type)

        if not has_delta:
            return "", False

        # Wrap delta events in the expected format
        # Note: No closing tag - this is continuation of the event stream
        return delta_str, True

    def mark_event_stream_synced(self, call_type: str) -> None:
        """
        Mark that the event stream has been synced to a session cache.

        Called after sending events to a session cache.

        Args:
            call_type: The type of LLM call
        """
        from core.event_stream.event_stream_manager import EventStreamManager

        event_stream_manager: EventStreamManager = self.state_manager.event_stream_manager
        stream = event_stream_manager.get_stream()

        if stream:
            stream.mark_session_synced(call_type)

    def reset_event_stream_sync(self, call_type: str) -> None:
        """
        Reset the session sync point for the event stream.

        Called when a session cache is invalidated/recreated.

        Args:
            call_type: The type of LLM call
        """
        from core.event_stream.event_stream_manager import EventStreamManager

        event_stream_manager: EventStreamManager = self.state_manager.event_stream_manager
        stream = event_stream_manager.get_stream()

        if stream:
            stream.reset_session_sync(call_type)

    def get_gui_event_stream(self) -> str:
        """
        Get the GUI event stream content for inclusion in user prompts.
        """
        gui_event_stream: str = GUIHandler.gui_module.get_gui_event_stream()
        if gui_event_stream:
            return (
                "<gui_event_stream>\n"
                "Use the GUI event stream to understand the current situation and past GUI actions:\n"
                f"{gui_event_stream}\n"
                "</gui_event_stream>"
            )
        return "<gui_event_stream>\n(no GUI events yet)\n</gui_event_stream>"

    def get_task_state(self) -> str:
        """
        Get the current task state for inclusion in user prompts.

        KV CACHING OPTIMIZATION:
        - This method returns STATIC content only (task name, instruction, mode, skills)
        - Todos are NOT included here - they are in the event stream via _emit_todos_event()
        - This ensures KV cache hits since task state doesn't change during execution
        """
        current_task: Optional[Task] = STATE.current_task

        if current_task:
            # Check if this is a simple task
            is_simple = getattr(current_task, "mode", "complex") == "simple"

            if is_simple:
                # Simple task - streamlined output
                return (
                    "<current_task>\n"
                    f"Task: {current_task.name} [SIMPLE MODE]\n"
                    f"Instruction: {current_task.instruction}\n"
                    "Mode: Simple task - execute directly, no todos required\n"
                    "</current_task>"
                )

            # Complex task - static info only (todos are in event stream)
            lines = [
                "<current_task>",
                f"Task: {current_task.name}",
                f"Instruction: {current_task.instruction}",
                "Mode: Complex task - use todos in event stream to track progress",
            ]

            # Add skill instructions if present (static for task duration)
            skill_instructions = self.get_skill_instructions()
            if skill_instructions:
                lines.append("")
                lines.append(skill_instructions)

            lines.append("</current_task>")
            return "\n".join(lines)
        return "<current_task>\n(no active task)\n</current_task>"

    def get_skill_instructions(self) -> str:
        """
        Get instructions from skills selected for the current task.

        Returns:
            Formatted skill instructions string, or empty string if no skills.
        """
        current_task: Optional[Task] = STATE.current_task

        if not current_task:
            return ""

        selected_skills = getattr(current_task, "selected_skills", [])
        if not selected_skills:
            return ""

        try:
            from core.skill.skill_manager import skill_manager
            instructions = skill_manager.get_skill_instructions(selected_skills)

            if not instructions:
                return ""

            return (
                "<active_skills>\n"
                "Follow these skill instructions for this task:\n\n"
                f"{instructions}\n"
                "</active_skills>"
            )
        except ImportError:
            return ""
        except Exception as e:
            logger.warning(f"[SKILLS] Failed to get skill instructions: {e}")
            return ""

    def get_agent_state(self) -> str:
        """
        Get the current agent state for inclusion in user prompts.
        """
        agent_properties = STATE.get_agent_properties()
        gui_mode_status = "GUI mode" if STATE.gui_mode else "CLI mode"

        if agent_properties:
            return (
                "<agent_state>\n"
                f"- Active Task ID: {agent_properties.get('current_task_id')}\n"
                f"- Current Mode: {gui_mode_status}\n"
                "</agent_state>"
            )
        return f"<agent_state>\n- Current Mode: {gui_mode_status}\n</agent_state>"

    # ──────────────────────── USER MESSAGE COMPONENTS ────────────────────────

    def create_user_query(self, query):
        """
        The direct user request or question.
        """
        return f"User Query: {query}"

    def create_user_expected_output(self, expected_format):
        """
        The final structure or format that we expect from the LLM response.
        """
        if not expected_format:
            return "No specific format requested."
        return f"Expected Output Format:\n{expected_format}"

    # ──────────────────────── MAKE PROMPT (STATIC SYSTEM ONLY) ────────────────────────
    def make_prompt(
        self,
        query=None,
        expected_format=None,
        system_flags=None,
        user_flags=None,
    ):
        """
        Assembles the system and user messages for the LLM with configurable sections.

        KV CACHING OPTIMIZATION:
        - System prompt contains ONLY STATIC content (agent_info, role_info, policy, environment, base_instruction)
        - Dynamic content (event_stream, task_state, agent_state) must be added to user prompts by callers
        - Use get_event_stream(), get_task_state(), get_agent_state(), get_gui_event_stream() for user prompts

        :param system_flags: Optional dict of booleans to enable/disable system sections.
            Supported keys (STATIC ONLY): ``agent_info``, ``role_info``, ``policy``,
            ``environment`` and ``base_instruction``.
        :param user_flags: Optional dict of booleans to enable/disable user sections.
            Supported keys: ``query`` and ``expected_output``. Defaults to ``query``
            enabled and ``expected_output`` disabled.
        """

        # System prompt: STATIC ONLY for KV caching
        system_default_flags = {
            "role_info": True,
            "agent_info": True,
            "policy": False,  # default off to save tokens
            "environment": True,
            "base_instruction": True,
        }
        user_default_flags = {
            "query": True,
            "expected_output": False,
        }

        system_flags = {**system_default_flags, **(system_flags or {})}
        user_flags = {**user_default_flags, **(user_flags or {})}

        # STATIC system sections only - ordered for maximum KV cache benefit
        system_sections = [
            ("agent_info", self.create_system_agent_info),
            ("policy", self.create_system_policy),
            ("role_info", self.create_system_role_info),
            ("environment", self.create_system_environmental_context),
            ("base_instruction", self.create_system_base_instruction),
        ]

        system_content_list = []
        for key, section_fn in system_sections:
            if system_flags.get(key):
                section_content = section_fn()
                if section_content:
                    system_content_list.append(section_content)

        system_message_content = "\n".join(system_content_list).strip()

        user_sections = [
            ("query", lambda: self.create_user_query(query)),
            ("expected_output", lambda: self.create_user_expected_output(expected_format)),
        ]

        user_content_list = []
        for key, section_fn in user_sections:
            if user_flags.get(key):
                section_content = section_fn()
                if section_content:
                    user_content_list.append(section_content)

        user_message_content = "\n\n".join(user_content_list).strip()

        return system_message_content, user_message_content