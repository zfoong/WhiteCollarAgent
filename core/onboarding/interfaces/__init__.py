# -*- coding: utf-8 -*-
"""
Abstract interfaces for onboarding implementations.

These interfaces define the contract that any UI implementation
(TUI, browser, future interfaces) must follow to provide onboarding.
"""

from core.onboarding.interfaces.base import OnboardingInterface
from core.onboarding.interfaces.steps import (
    HardOnboardingStep,
    StepResult,
    ProviderStep,
    ApiKeyStep,
    UserNameStep,
    AgentNameStep,
    MCPStep,
    SkillsStep,
)

__all__ = [
    "OnboardingInterface",
    "HardOnboardingStep",
    "StepResult",
    "ProviderStep",
    "ApiKeyStep",
    "UserNameStep",
    "AgentNameStep",
    "MCPStep",
    "SkillsStep",
]
