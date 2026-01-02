from core.action.action_framework.registry import action

@action(
    name="get current time",
    description="This action retrieves the current date and time in a standardized format and returns it as a JSON object. It utilizes the `datetime` module in Python to obtain the current time and formats it into a string representation that includes the year, month, day, hour, minute, and second. This action is designed to provide a reliable and consistent time reference for other actions or processes that require a timestamp.",
    mode="CLI",
    input_schema={},
    output_schema={
        "time": {
            "type": "string",
            "example": "2024-10-27 10:30:00",
            "description": "The current date and time in YYYY-MM-DD HH:MM:SS format"
        }
    },
    test_payload={
        "simulated_mode": True
    }
)
def get_current_time(input_data: dict) -> dict:
    import json
    from datetime import datetime

    datetime_obj = datetime.now()
    formatted_time = datetime_obj.strftime('%Y-%m-%d %H:%M:%S')

    result = {
        "status": "success",
        "time": formatted_time
    }

    return result