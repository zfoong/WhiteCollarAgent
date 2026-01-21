from core.action.action_framework.registry import action

@action(
        name="mark task cancel",
        description="End the current task for this session as CANCELLED. Use this when the user aborts the task.",
        default=True,
        mode="CLI",
        input_schema={
                "reason": {
                        "type": "string",
                        "example": "User requested to stop.",
                        "description": "Optional reason for cancellation."
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
                "reason": "User requested to stop.",
                "simulated_mode": True
        }
)
def mark_task_cancel(input_data: dict) -> dict:
    import json, asyncio

    reason = input_data.get('reason')
    simulated_mode = input_data.get('simulated_mode', False)
    
    # In simulated mode, skip the actual interface call for testing
    if not simulated_mode:
        import core.internal_action_interface as iai
        res = asyncio.run(iai.InternalActionInterface.mark_task_cancel(reason=reason))
        # Convert 'ok' to 'success' for test compatibility
        if isinstance(res, dict) and res.get('status') == 'ok':
            res['status'] = 'success'
    else:
        res = {'status': 'success', 'task_id': 'test_task_id'}
    
    return res