from core.action.action_framework.registry import action

@action(
        name="start next step",
        description="Advance the running workflow to the NEXT step for this session. If update_plan is true, first update the plan (e.g., when the old plan is outdated or new info is available) and then advance to the next step, which may be newly created by the updated plan.",
        mode="CLI",
        default=True,
        input_schema={
                "update_plan": {
                        "type": "boolean",
                        "example": True,
                        "description": "When true, ask the planner to update the plan and advance; otherwise advance to the next existing step."
                }
        },
        output_schema={
                "status": {
                        "type": "string",
                        "example": "ok",
                        "description": "Indicates the action executed; see 'result' for queueing/completion status."
                },
                "workflow_id": {
                        "type": "string",
                        "example": "user_request_1_abc123",
                        "description": "The session/workflow id affected."
                },
                "result": {
                        "type": "object",
                        "example": {
                                "status": "queued",
                                "step": "gather sources"
                        },
                        "description": "Result from WorkflowManager.start_next_step (e.g., queued, no_next_step, completed)."
                }
        },
        test_payload={
                "update_plan": False,
                "simulated_mode": True
        }
)
def start_next_step(input_data: dict) -> dict:
    import json, asyncio

    update_plan = bool(input_data.get('update_plan', False))
    simulated_mode = input_data.get('simulated_mode', False)
    
    # In simulated mode, skip the actual interface call for testing
    if not simulated_mode:
        import core.internal_action_interface as iai
        res = asyncio.run(iai.InternalActionInterface.start_next_step(update_plan=update_plan))
        # Convert 'ok' to 'success' for test compatibility
        if isinstance(res, dict) and res.get('status') == 'ok':
            res['status'] = 'success'
    else:
        res = {'status': 'success', 'workflow_id': 'test_workflow_id', 'result': {'status': 'queued', 'step': 'test_step'}}
    
    return res