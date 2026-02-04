from core.action.action_framework.registry import action

@action(
    name="describe_image",
    description="Uses a Visual Language Model to analyse an image and return a detailed, markdown-ready description.",
    mode="CLI",
    action_sets=["document_processing"],
    input_schema={
        "image_path": {
            "type": "string",
            "example": "C:\\\\Users\\\\user\\\\Pictures\\\\sample.jpg",
            "description": "Absolute path to the image file."
        },
        "prompt": {
            "type": "string",
            "example": "Highlight objects, colours and spatial relationships.",
            "description": "Optional user prompt refining what the VLM should describe."
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success",
            "description": "'success' if the description was generated, 'error' otherwise."
        },
        "description": {
            "type": "string",
            "example": "A photo of a golden retriever sitting on a red sofa...",
            "description": "Markdown-friendly textual description returned by the VLM."
        },
        "message": {
            "type": "string",
            "example": "File not found.",
            "description": "Error message if applicable."
        }
    },
    test_payload={
        "image_path": "C:\\\\Users\\\\user\\\\Pictures\\\\sample.jpg",
        "prompt": "Highlight objects, colours and spatial relationships.",
        "simulated_mode": True
    }
)
def view_image(input_data: dict) -> dict:
    import json, os

    image_path = str(input_data.get('image_path', '')).strip()
    simulated_mode = input_data.get('simulated_mode', False)
    prompt = str(input_data.get('prompt', '')).strip() or None

    if simulated_mode:
        # Return mock result for testing
        return {'status': 'success', 'description': 'A simulated image description showing various objects and colors.', 'message': ''}

    if not image_path:
        return {'status': 'error', 'description': '', 'message': 'image_path is required.'}

    if not os.path.isfile(image_path):
        return {'status': 'error', 'description': '', 'message': 'File not found.'}

    try:
        import core.internal_action_interface as iai
        description = iai.InternalActionInterface.describe_image(image_path, prompt)
        return {'status': 'success', 'description': description, 'message': ''}
    except Exception as e:
        return {'status': 'error', 'description': '', 'message': str(e)}