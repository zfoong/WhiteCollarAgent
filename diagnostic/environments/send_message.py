"""Diagnostic environment for the "send_message" action."""

from __future__ import annotations

from diagnostic.framework import ActionTestCase


def get_test_case() -> ActionTestCase:
    return ActionTestCase(
        name="send_message",
        base_input={},
        skip_reason=(
            "Requires InternalActionInterface.do_chat to communicate with the host conversation service."
        ),
    )
