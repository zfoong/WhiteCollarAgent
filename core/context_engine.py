from datetime import datetime, timezone

from tzlocal import get_localzone
import json

from core.config import AGENT_WORKSPACE_ROOT
from core.logger import logger
from core.prompt import (
    AGENT_ROLE_PROMPT,
    AGENT_INFO_PROMPT,
    AGENT_STATE_PROMPT,
    ENVIRONMENTAL_CONTEXT_PROMPT,
    POLICY_PROMPT,
)
from core.state.state_manager import StateManager
from core.state.agent_state import STATE
from typing import Optional, Dict, Any

"""
core.context_engine

The main context engine that constructs
system prompt and user prompt. System prompt for agent roles are overwrite
by specialise agent.
"""

class ContextEngine:
    """Build structured prompts for the LLM from runtime state.

    The engine centralizes all context-building logic so callers can request a
    ready-to-send pair of system and user messages without worrying about where
    the information originates (conversation history, event stream, etc.).
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
        
    # ─────────────── SYSTEM MESSAGE COMPONENTS ───────────────

    def create_system_agent_info(self):
        """
        Create a system message block describing the CraftOS, agent's identity and mechanism.
        """
        # prompt = RESOLVE_ACTION_INPUT_PROMPT.format()
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
        """
        if self._role_info_func:
            role = self._role_info_func()
            return AGENT_ROLE_PROMPT.format(role=role)
        return AGENT_ROLE_PROMPT.format(role="You are an AI agent, named 'white collar agent', developed by CraftOS, a general computer-use AI agent that can switch between CLI/GUI mode.")

    def create_system_agent_state(self):
        """Return formatted agent properties for the current session."""
        agent_properties = STATE.get_agent_properties()

        if agent_properties:
            prompt = AGENT_STATE_PROMPT.format(
                current_task_id=agent_properties.get("current_task_id"),
                action_count=agent_properties.get("action_count", 0),
                max_actions_per_task=agent_properties.get("max_actions_per_task"),
                token_count=agent_properties.get("token_count", 0),
                max_tokens_per_task=agent_properties.get("max_tokens_per_task"),
            )
            return (
                "\nThe current agent state is as follows:"
                f"\n{prompt}"
            )
        return ""

    def create_system_conversation_history(self):
        """Return formatted conversation history for the current session."""

        conversation_state = STATE.conversation_state

        if conversation_state:
            return (
                "\nThis is the conversation history (from oldest to newest messages):"
                f"\n{conversation_state}"
            )
        return "There is no stored conversation history for the current session yet."

    def create_system_event_stream_state(self):
        """Return formatted event stream context for the current session."""

        event_stream = STATE.event_stream

        if event_stream:
            return (
                "\nUse the event stream to understand the current situation, past agent actions to craft the input parameters:\nEvent stream (oldest to newest):"
                f"\n{event_stream}"
            )
        return ""

    def create_system_task_state(self):
        """Return formatted task/plan state for the current session."""

        current_task: Optional[Task] = STATE.current_task

        if current_task:
            current_task_dict: Dict[str, Any] = current_task.to_dict(fold=True, current_step_index=STATE.agent_properties.get_property("current_step_index"))
            return "\nThe plan of the current on-going task:" + f"\n{json.dumps(current_task_dict, indent=4)}"
        return ""

    def create_system_policy(self):
        """
        Create a system message block with constraints: safety, compliance, privacy, do/don't lists, etc.
        """
        prompt = POLICY_PROMPT
        return prompt

    def create_system_environmental_context(self):
        """
        Create a system message block with environmental & temporal context
        """
        local_timezone = get_localzone()
        now = datetime.now(local_timezone)
        current_time = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00","Z")
        prompt = ENVIRONMENTAL_CONTEXT_PROMPT.format(
            current_time=current_time, 
            timezone=now.strftime('%Z'),
            user_location=local_timezone, # TODO Not accurate! 
            working_directory=AGENT_WORKSPACE_ROOT
            )
        return prompt
    
    def create_system_base_instruction(self):
        """
        Create a system message of instruction.
        """
        return "Please assist the user using the context given in the conversation or event stream"


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

    # ──────────────────────── MAKE PROMPT ────────────────────────
    def make_prompt(
        self,
        query=None,
        expected_format=None,
        system_flags=None,
        user_flags=None,
    ):
        """
        Assembles the system and user messages for the LLM with configurable sections.

        :param system_flags: Optional dict of booleans to enable/disable system sections.
            Supported keys: ``agent_info``, ``role_info``, ``conversation_history``,
            ``event_stream``, ``task_state``, ``policy``, ``environment`` and
            ``base_instruction``. Defaults to all enabled except ``policy``.
        :param user_flags: Optional dict of booleans to enable/disable user sections.
            Supported keys: ``query`` and ``expected_output``. Defaults to ``query``
            enabled and ``expected_output`` disabled.
        """

        system_default_flags = {
            "role_info": True,
            "agent_info": True,
            "agent_state": self.state_manager.is_running_task(),
            "conversation_history": True,
            "event_stream": True,
            "task_state": True,
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

        system_sections = [
            ("role_info", self.create_system_role_info),
            ("agent_info", self.create_system_agent_info),
            ("agent_state", self.create_system_agent_state),
            ("conversation_history", self.create_system_conversation_history),
            ("event_stream", self.create_system_event_stream_state),
            ("task_state", self.create_system_task_state),
            ("policy", self.create_system_policy),
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