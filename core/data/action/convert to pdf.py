from core.action.action_framework.registry import action

@action(
    name="convert to pdf",
    description="Converts a .txt, .md, or .docx file into a PDF using Pandoc (xelatex backend) and saves it at the specified location. Validates dependencies first.",
    platforms=["linux"],
    input_schema={
        "input_file": {
            "type": "string",
            "example": "/path/to/input.md",
            "description": "Path to the input file (txt, md, docx)."
        },
        "output_pdf": {
            "type": "string",
            "example": "/path/to/output.pdf",
            "description": "Path where the PDF will be saved."
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success",
            "description": "'success' if file was created, 'error' otherwise."
        },
        "pdf_file": {
            "type": "string",
            "example": "/path/to/output.pdf",
            "description": "Path to the generated PDF (on success)."
        },
        "message": {
            "type": "string",
            "example": "Missing dependency: pandoc",
            "description": "Error details (only on failure)."
        }
    },
    test_payload={
        "input_file": "/path/to/input.md",
        "output_pdf": "/path/to/output.pdf",
        "simulated_mode": True
    }
)
def convert_to_pdf_linux(input_data: dict) -> dict:
    import os, sys, json, subprocess

    def _check_dep(cmd):
        try:
            subprocess.check_output([cmd, '--version'], stderr=subprocess.STDOUT)
            return True
        except Exception:
            return False


    simulated_mode = input_data.get('simulated_mode', False)
    
    input_file = input_data.get('input_file')
    output_pdf = input_data.get('output_pdf')

    # Validate input file
    if not input_file or not os.path.isfile(input_file):
        if simulated_mode:
            return {"status": "success", "pdf_file": output_pdf or input_file.replace('.md', '.pdf')}
        return {"status": "error", "message": "Valid input_file required."}

    # Build default output path
    if not output_pdf:
        base, _ = os.path.splitext(input_file)
        output_pdf = base + '.pdf'

    if simulated_mode:
        # Return mock result for testing
        return {"status": "success", "pdf_file": output_pdf}

    # Ensure output directory
    os.makedirs(os.path.dirname(output_pdf), exist_ok=True)

    # Dependency checks
    if not _check_dep('pandoc'):
        return {"status": "error", "message": "Missing dependency: pandoc"}
    if not _check_dep('xelatex'):
        return {"status": "error", "message": "Missing dependency: xelatex"}

    # Attempt conversion
    try:
        subprocess.check_call([
            'pandoc', input_file, '-o', output_pdf,
            '--pdf-engine=xelatex',
            '--standalone'
        ])
        return {"status": "success", "pdf_file": output_pdf}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@action(
    name="convert to pdf",
    description="Converts a .txt, .md, or .docx file into a PDF using Pandoc (xelatex backend) and saves it at the specified location. Validates dependencies first.",
    platforms=["windows"],
    input_schema={
        "input_file": {
            "type": "string",
            "example": "/path/to/input.md",
            "description": "Path to the input file (txt, md, docx)."
        },
        "output_pdf": {
            "type": "string",
            "example": "/path/to/output.pdf",
            "description": "Path where the PDF will be saved."
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success",
            "description": "'success' if file was created, 'error' otherwise."
        },
        "pdf_file": {
            "type": "string",
            "example": "/path/to/output.pdf",
            "description": "Path to the generated PDF (on success)."
        },
        "message": {
            "type": "string",
            "example": "Missing dependency: pandoc",
            "description": "Error details (only on failure)."
        }
    },
    test_payload={
        "input_file": "/path/to/input.md",
        "output_pdf": "/path/to/output.pdf",
        "simulated_mode": True
    }
)
def convert_to_pdf_windows(input_data: dict) -> dict:
    import os, sys, json, subprocess

    def _check_dep(cmd):
        try:
            subprocess.check_output([cmd, '--version'], stderr=subprocess.STDOUT, shell=True)
            return True
        except Exception:
            return False


    simulated_mode = input_data.get('simulated_mode', False)
    
    input_file = input_data.get('input_file')
    output_pdf = input_data.get('output_pdf')

    if not input_file or not os.path.isfile(input_file):
        if simulated_mode:
            return {"status": "success", "pdf_file": output_pdf or input_file.replace('.md', '.pdf')}
        return {"status": "error", "message": "Valid input_file required."}

    if not output_pdf:
        base, _ = os.path.splitext(input_file)
        output_pdf = base + '.pdf'

    if simulated_mode:
        return {"status": "success", "pdf_file": output_pdf}

    os.makedirs(os.path.dirname(output_pdf), exist_ok=True)

    if not _check_dep('pandoc'):
        return {"status": "error", "message": "Missing dependency: pandoc"}
    if not _check_dep('xelatex'):
        return {"status": "error", "message": "Missing dependency: xelatex (MiKTeX/TeXLive)"}

    try:
        subprocess.check_call([
            'pandoc', input_file, '-o', output_pdf,
            '--pdf-engine=xelatex',
            '--standalone'
        ], shell=True)
        return {"status": "success", "pdf_file": output_pdf}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@action(
    name="convert to pdf",
    description="Converts a .txt, .md, or .docx file into a PDF using Pandoc (xelatex backend) and saves it at the specified location. Validates dependencies first.",
    platforms=["darwin"],
    input_schema={
        "input_file": {
            "type": "string",
            "example": "/path/to/input.md",
            "description": "Path to the input file (txt, md, docx)."
        },
        "output_pdf": {
            "type": "string",
            "example": "/path/to/output.pdf",
            "description": "Path where the PDF will be saved."
        }
    },
    output_schema={
        "status": {
            "type": "string",
            "example": "success",
            "description": "'success' if file was created, 'error' otherwise."
        },
        "pdf_file": {
            "type": "string",
            "example": "/path/to/output.pdf",
            "description": "Path to the generated PDF (on success)."
        },
        "message": {
            "type": "string",
            "example": "Missing dependency: pandoc",
            "description": "Error details (only on failure)."
        }
    },
    test_payload={
        "input_file": "/path/to/input.md",
        "output_pdf": "/path/to/output.pdf",
        "simulated_mode": True
    }
)
def convert_to_pdf_darwin(input_data: dict) -> dict:
    import os, sys, json, subprocess

    def _check_dep(cmd):
        try:
            subprocess.check_output([cmd, '--version'], stderr=subprocess.STDOUT)
            return True
        except Exception:
            return False


    def _execute_action():
        input_file = input_data.get('input_file')
        output_pdf = input_data.get('output_pdf')

        if not input_file or not os.path.isfile(input_file):
            output = (json.dumps({"status": "error", "message": "Valid input_file required."}))
            return

        if not output_pdf:
            base, _ = os.path.splitext(input_file)
            output_pdf = base + '.pdf'

        os.makedirs(os.path.dirname(output_pdf), exist_ok=True)

        if not _check_dep('pandoc'):
            output = (json.dumps({"status": "error", "message": "Missing dependency: pandoc"}))
            return
        if not _check_dep('xelatex'):
            output = (json.dumps({"status": "error", "message": "Missing dependency: xelatex (MacTeX required)"}))
            return

        try:
            subprocess.check_call([
                'pandoc', input_file, '-o', output_pdf,
                '--pdf-engine=xelatex',
                '--standalone'
            ])
            output = (json.dumps({"status": "success", "pdf_file": output_pdf}))
        except Exception as e:
            output = (json.dumps({"status": "error", "message": str(e)}))

    _execute_action()