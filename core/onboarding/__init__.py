# -*- coding: utf-8 -*-
"""
Onboarding module for first-time setup and user profile configuration.

Provides:
- Hard onboarding: UI-driven multi-step wizard for initial configuration
- Soft onboarding: Conversational Q&A interview for user profile
- Modular interface abstraction for different UI implementations
"""

from core.onboarding.config import (
    ONBOARDING_CONFIG_FILE,
    HARD_ONBOARDING_STEPS,
    DEFAULT_AGENT_NAME,
)
from core.onboarding.state import OnboardingState, load_state, save_state
from core.onboarding.manager import OnboardingManager, onboarding_manager

__all__ = [
    "ONBOARDING_CONFIG_FILE",
    "HARD_ONBOARDING_STEPS",
    "DEFAULT_AGENT_NAME",
    "OnboardingState",
    "load_state",
    "save_state",
    "OnboardingManager",
    "onboarding_manager",
]
