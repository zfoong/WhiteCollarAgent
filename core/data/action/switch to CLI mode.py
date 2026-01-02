from core.action.action_framework.registry import action

@action(
    name="switch to CLI mode",
    description="Switch the agent to CLI mode by setting gui_mode to False in the current StateSession via InternalActionInterface.switch_to_CLI_mode(). Use when the agent should operate without GUI screen control.",
    mode="GUI",
    default=True,
    input_schema={},
    output_schema={
        "status": {
            "type": "string",
            "example": "ok",
            "description": "Result status: 'ok' or 'error'."
        },
        "gui_mode": {
            "type": "boolean",
            "example": False,
            "description": "Target GUI mode after the switch (False means CLI mode)."
        },
        "error": {
            "type": "string",
            "example": "StateSession not initialized",
            "description": "Error message (present when status == 'error')."
        }
    },
    test_payload={
        "simulated_mode": False
    }
)
def switch_to_cli_mode(input_data: dict) -> dict:
    import json
    import core.internal_action_interface as iai
    
    simulated_mode = input_data.get('simulated_mode', False)
    
    try:
        if not simulated_mode:
            iai.InternalActionInterface.switch_to_CLI_mode()
        return {"status": "ok", "gui_mode": False}
    except Exception as e:
        return {"status": "error", "error": str(e)}