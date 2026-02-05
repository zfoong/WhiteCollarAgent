from core.action.action_framework.registry import action

@action(
    name="set_mode",
    description="Switch the agent between CLI and GUI modes. CLI mode operates without screen control; GUI mode enables screen interaction capabilities.",
    mode="ALL",
    default=True,
    action_sets=["core"],
    input_schema={
        "target_mode": {
            "type": "string",
            "example": "cli",
            "description": "Target mode to switch to: 'cli' or 'gui'."
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "ok",
            "description": "Result status: 'ok' or 'error'."
        },
        "gui_mode": {
            "type": "boolean",
            "example": False,
            "description": "Current GUI mode after the operation (True = GUI, False = CLI)."
        },
        "message": {
            "type": "string",
            "example": "Successfully switched to CLI mode.",
            "description": "Status message."
        },
        "error": {
            "type": "string",
            "example": "StateSession not initialized",
            "description": "Error message (present when status == 'error')."
        }
    },
    test_payload={
        "target_mode": "cli",
        "simulated_mode": False
    }
)
def set_mode(input_data: dict) -> dict:
    import core.internal_action_interface as iai
    from core.state.agent_state import STATE

    target_mode = str(input_data.get('target_mode', '')).strip().lower()
    simulated_mode = input_data.get('simulated_mode', False)

    if target_mode not in ('cli', 'gui'):
        return {
            "status": "error",
            "error": f"Invalid target_mode '{target_mode}'. Must be 'cli' or 'gui'.",
            "gui_mode": STATE.gui_mode
        }

    try:
        target_gui_mode = (target_mode == 'gui')

        # Check if already in target mode
        if STATE.gui_mode == target_gui_mode:
            mode_name = "GUI" if target_gui_mode else "CLI"
            return {
                "status": "ok",
                "gui_mode": target_gui_mode,
                "message": f"Already in {mode_name} mode. No change needed."
            }

        # Perform the switch
        if not simulated_mode:
            if target_gui_mode:
                iai.InternalActionInterface.switch_to_GUI_mode()
            else:
                iai.InternalActionInterface.switch_to_CLI_mode()

        mode_name = "GUI" if target_gui_mode else "CLI"
        return {
            "status": "ok",
            "gui_mode": target_gui_mode,
            "message": f"Successfully switched to {mode_name} mode."
        }

    except Exception as e:
        return {"status": "error", "error": str(e), "gui_mode": STATE.gui_mode}
