from core.action.action_framework.registry import action

@action(
        name="mark task completed",
        description="End the current task for this session as COMPLETED. Use this when the task is fully done and outputs are satisfactory.",
        default=True,
        input_schema={
                "message": {
                        "type": "string",
                        "example": "All steps executed successfully.",
                        "description": "Optional completion note to persist in logs."
                }
        },
        output_schema={
                "status": {
                        "type": "string",
                        "example": "ok",
                        "description": "Result of the operation."
                },
                "task_id": {
                        "type": "string",
                        "example": "user_request_1_abc123",
                        "description": "The session/task id affected."
                }
        },
        test_payload={
                "message": "All steps executed successfully.",
                "simulated_mode": True
        }
)
def mark_task_completed(input_data: dict) -> dict:
    import json, asyncio

    message = input_data.get('message')
    simulated_mode = input_data.get('simulated_mode', False)
    
    # In simulated mode, skip the actual interface call for testing
    if not simulated_mode:
        import core.internal_action_interface as iai
        res = asyncio.run(iai.InternalActionInterface.mark_task_completed(message=message))
        # Convert 'ok' to 'success' for test compatibility
        if isinstance(res, dict) and res.get('status') == 'ok':
            res['status'] = 'success'
    else:
        res = {'status': 'success', 'task_id': 'test_task_id'}
    
    return res