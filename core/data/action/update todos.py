from core.action.action_framework.registry import action

@action(
    name="update todos",
    description=(
        "Update the todo list for the current task. The todo list follows a structured workflow:\n"
        "1. Acknowledge task receipt (send message to user)\n"
        "2. Collect information (gather what's needed before execution)\n"
        "3. Execute task steps (the actual work)\n"
        "4. Verify outcome (check if result meets requirements)\n"
        "5. Confirm with user (get approval before ending)\n"
        "6. Clean up (delete temp files if any)\n\n"
        "Always provide the COMPLETE todo list. Mark items as 'in_progress' when starting, 'completed' when done."
    ),
    mode="ALL",
    default=True,
    input_schema={
        "todos": {
            "type": "array",
            "description": "The complete todo list following the workflow: acknowledge -> collect info -> execute -> verify -> confirm -> cleanup.",
            "example": [
                {"content": "Acknowledge task and confirm understanding with user", "status": "completed"},
                {"content": "Collect information: user's preferred format, data sources", "status": "completed"},
                {"content": "Execute: Fetch weather data from reliable source", "status": "in_progress"},
                {"content": "Execute: Format the weather report", "status": "pending"},
                {"content": "Verify: Check report accuracy and completeness", "status": "pending"},
                {"content": "Confirm: Send result to user and await approval", "status": "pending"},
                {"content": "Clean up: Remove temporary files", "status": "pending"}
            ],
            "items": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "What needs to be done. Prefix with phase: 'Acknowledge:', 'Collect:', 'Execute:', 'Verify:', 'Confirm:', 'Cleanup:'"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed"],
                        "description": "pending=not started, in_progress=working on it, completed=done"
                    }
                },
                "required": ["content", "status"]
            }
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success",
            "description": "Indicates if the update was successful"
        },
        "todos": {
            "type": "array",
            "description": "The updated todo list"
        }
    },
    test_payload={
        "todos": [
            {"content": "Acknowledge task and confirm understanding", "status": "completed"},
            {"content": "Collect: Identify required data sources", "status": "in_progress"},
            {"content": "Execute: Process the data", "status": "pending"},
            {"content": "Verify: Validate output correctness", "status": "pending"},
            {"content": "Confirm: Get user approval", "status": "pending"}
        ],
        "simulated_mode": True
    }
)
def update_todos(input_data: dict) -> dict:
    """Update the todo list for the current task."""
    todos = input_data.get("todos", [])
    simulated_mode = input_data.get("simulated_mode", False)

    if not simulated_mode:
        import core.internal_action_interface as iai
        result = iai.InternalActionInterface.update_todos(todos)
        if result.get("status") == "ok":
            result["status"] = "success"
        return result

    return {"status": "success", "todos": todos}
