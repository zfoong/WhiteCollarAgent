from core.action.action_framework.registry import action


@action(
    name="task_end",
    description=(
        "End the current task for this session with a final status. "
        "Use status='complete' when the task is fully done, or 'abort' when it "
        "should be cancelled/failed early. Always provide a brief reason."
    ),
    default=True,
    mode="CLI",
    action_sets=["core"],
    input_schema={
        "status": {
            "type": "string",
            "enum": ["complete", "abort"],
            "example": "complete",
            "description": "Final status for the task: 'complete' or 'abort'.",
        },
        "reason": {
            "type": "string",
            "example": "All todos completed successfully.",
            "description": "Why the task is considered complete or why it should be aborted.",
        },
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success",
            "description": "Result of the operation.",
        },
        "task_id": {
            "type": "string",
            "example": "user_request_1_abc123",
            "description": "The session/task id affected.",
        },
    },
    test_payload={
        "status": "complete",
        "reason": "All todos completed successfully.",
        "simulated_mode": True,
    },
)
def end_task(input_data: dict) -> dict:
    import asyncio

    status = (input_data.get("status") or "").strip().lower()
    reason = input_data.get("reason")
    simulated_mode = input_data.get("simulated_mode", False)

    if status not in ("complete", "abort"):
        return {
            "status": "error",
            "message": "Invalid status for end task. Use 'complete' or 'abort'.",
        }

    # In simulated mode, skip the actual interface call for testing
    if simulated_mode:
        return {"status": "success", "task_id": "test_task_id"}

    import core.internal_action_interface as iai

    if status == "complete":
        res = asyncio.run(iai.InternalActionInterface.mark_task_completed(message=reason))
    else:
        # Map 'abort' to a cancellation by default
        res = asyncio.run(iai.InternalActionInterface.mark_task_cancel(reason=reason))

    if isinstance(res, dict) and res.get("status") == "ok":
        res["status"] = "success"

    return res

