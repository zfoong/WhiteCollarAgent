from core.action.action_framework.registry import action

@action(
        name="ask question",
        description="Use this action to ask a clarifying question to the user when more information is needed.",
        execution_mode="internal",
        input_schema={
                "question": {
                        "type": "string",
                        "example": "What's your email address?",
                        "description": "The question to ask the user."
                },
                "wait_for_user_reply": {
                        "type": "boolean",
                        "example": True,
                        "description": "True if this action require user's response to proceed. For example, true if you ask a question in the message."
                }
        },
        output_schema={
                "status": {
                        "type": "string",
                        "example": "ok",
                        "description": "Indicates the action completed successfully."
                },
                "question": {
                        "type": "string",
                        "example": "What's your email address?",
                        "description": "The question that was asked to the user."
                },
                "fire_at_delay": {
                        "type": "number",
                        "example": 10800,
                        "description": "Delay in seconds before the next follow-up action should be scheduled. 10800 seconds (3 hours) if wait_for_user_reply is true, otherwise 0."
                }
        },
        test_payload={
                "question": "What's your email address?",
                "wait_for_user_reply": False,
                "simulated_mode": True
        }
)
def ask_question(input_data: dict) -> dict:
    import json
    import asyncio
    
    question = input_data['question']
    wait_for_user_reply = bool(input_data.get('wait_for_user_reply', False))
    simulated_mode = input_data.get('simulated_mode', False)
    
    # In simulated mode, skip the actual interface call for testing
    if not simulated_mode:
        import core.internal_action_interface as internal_action_interface
        asyncio.run(internal_action_interface.InternalActionInterface.do_ask_question(question))
    
    fire_at_delay = 10800 if wait_for_user_reply else 0
    return {'status': 'success', 'question': question, 'fire_at_delay': fire_at_delay}