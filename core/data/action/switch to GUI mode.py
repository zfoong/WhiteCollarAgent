from core.action.action_framework.registry import action

@action(
    name="switch to GUI mode",
    description="Switch the agent to GUI mode by setting gui_mode to True in the current StateSession via InternalActionInterface.switch_to_GUI_mode(). Use when the agent should operate with GUI/screen control.",
    mode="CLI",
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
            "example": True,
            "description": "Target GUI mode after the switch (True means GUI mode)."
        },
        "message": {
            "type": "string",
            "example": "Successfully switched to GUI mode.",
            "description": "Status message indicating if the switch was successful or if already in GUI mode."
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
def switch_to_gui_mode(input_data: dict) -> dict:
    import json
    import core.internal_action_interface as iai
    from core.state.agent_state import STATE
    
    simulated_mode = input_data.get('simulated_mode', False)
    
    try:
        # Check if already in GUI mode
        if STATE.gui_mode:
            return {
                "status": "ok", 
                "gui_mode": True,
                "message": "Already in GUI mode. No change needed."
            }
        
        if not simulated_mode:
            iai.InternalActionInterface.switch_to_GUI_mode()
        return {
            "status": "ok", 
            "gui_mode": True,
            "message": "Successfully switched to GUI mode."
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "gui_mode": STATE.gui_mode}