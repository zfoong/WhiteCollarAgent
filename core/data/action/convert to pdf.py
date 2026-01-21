from core.action.action_framework.registry import action

@action(
    name="convert to pdf",
    description="Converts a .txt, .md, or .docx file into a PDF using Pandoc (xelatex backend) and saves it at the specified location. Validates dependencies first.",
    platforms=["linux"],
    mode="CLI",
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
    import os, sys, json, subprocess, shutil

    def _check_dep(cmd):
        try:
            subprocess.check_output([cmd, '--version'], stderr=subprocess.STDOUT, timeout=5)
            return True
        except Exception:
            return False

    def _ensure_system_dep(cmd, install_cmd):
        """Ensure a system dependency is installed, attempt installation if missing."""
        if _check_dep(cmd):
            return True
        
        # Try to install without sudo (will fail gracefully if permissions needed)
        try:
            subprocess.check_call(
                install_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120
            )
            # Verify installation succeeded
            return _check_dep(cmd)
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
    os.makedirs(os.path.dirname(output_pdf) if os.path.dirname(output_pdf) else '.', exist_ok=True)

    # Ensure dependencies are installed
    # Try apt first (Debian/Ubuntu)
    if shutil.which('apt-get'):
        if not _ensure_system_dep('pandoc', ['apt-get', 'install', '-y', 'pandoc']):
            return {"status": "error", "message": "Failed to install pandoc. Please install manually: sudo apt-get install pandoc"}
        if not _ensure_system_dep('xelatex', ['apt-get', 'install', '-y', 'texlive-xetex']):
            return {"status": "error", "message": "Failed to install xelatex. Please install manually: sudo apt-get install texlive-xetex"}
    # Try yum/dnf (RHEL/CentOS/Fedora)
    elif shutil.which('yum') or shutil.which('dnf'):
        pkg_mgr = 'dnf' if shutil.which('dnf') else 'yum'
        if not _ensure_system_dep('pandoc', [pkg_mgr, 'install', '-y', 'pandoc']):
            return {"status": "error", "message": f"Failed to install pandoc. Please install manually: sudo {pkg_mgr} install pandoc"}
        if not _ensure_system_dep('xelatex', [pkg_mgr, 'install', '-y', 'texlive-xetex']):
            return {"status": "error", "message": f"Failed to install xelatex. Please install manually: sudo {pkg_mgr} install texlive-xetex"}
    else:
        # Fallback: just check if installed
        if not _check_dep('pandoc'):
            return {"status": "error", "message": "Missing dependency: pandoc. Please install manually."}
        if not _check_dep('xelatex'):
            return {"status": "error", "message": "Missing dependency: xelatex. Please install manually."}

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
    mode="CLI",
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
    import os, sys, json, subprocess, shutil

    def _check_dep(cmd):
        try:
            subprocess.check_output([cmd, '--version'], stderr=subprocess.STDOUT, shell=True, timeout=5)
            return True
        except Exception:
            return False

    def _ensure_system_dep(cmd, install_cmd):
        """Ensure a system dependency is installed, attempt installation if missing."""
        if _check_dep(cmd):
            return True
        
        # Try to install via chocolatey if available
        if shutil.which('choco'):
            try:
                subprocess.check_call(
                    install_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=300,
                    shell=True
                )
                return _check_dep(cmd)
            except Exception:
                pass
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

    os.makedirs(os.path.dirname(output_pdf) if os.path.dirname(output_pdf) else '.', exist_ok=True)

    # Try to install via chocolatey if available
    if shutil.which('choco'):
        if not _ensure_system_dep('pandoc', ['choco', 'install', 'pandoc', '-y']):
            if not _check_dep('pandoc'):
                return {"status": "error", "message": "Missing dependency: pandoc. Install via: choco install pandoc"}
        if not _ensure_system_dep('xelatex', ['choco', 'install', 'miktex', '-y']):
            if not _check_dep('xelatex'):
                return {"status": "error", "message": "Missing dependency: xelatex. Install via: choco install miktex"}
    else:
        # Fallback: just check if installed
        if not _check_dep('pandoc'):
            return {"status": "error", "message": "Missing dependency: pandoc. Please install manually or install Chocolatey: choco install pandoc"}
        if not _check_dep('xelatex'):
            return {"status": "error", "message": "Missing dependency: xelatex (MiKTeX/TeXLive). Please install manually."}

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
    mode="CLI",
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
    import os, sys, json, subprocess, shutil

    def _check_dep(cmd):
        try:
            subprocess.check_output([cmd, '--version'], stderr=subprocess.STDOUT, timeout=5)
            return True
        except Exception:
            return False

    def _ensure_system_dep(cmd, install_cmd):
        """Ensure a system dependency is installed, attempt installation if missing."""
        if _check_dep(cmd):
            return True
        
        # Try to install via homebrew if available
        if shutil.which('brew'):
            try:
                subprocess.check_call(
                    install_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=300
                )
                return _check_dep(cmd)
            except Exception:
                pass
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

        os.makedirs(os.path.dirname(output_pdf) if os.path.dirname(output_pdf) else '.', exist_ok=True)

        # Try to install via homebrew if available
        if shutil.which('brew'):
            if not _ensure_system_dep('pandoc', ['brew', 'install', 'pandoc']):
                if not _check_dep('pandoc'):
                    output = (json.dumps({"status": "error", "message": "Missing dependency: pandoc. Install via: brew install pandoc"}))
                    return
            if not _ensure_system_dep('xelatex', ['brew', 'install', '--cask', 'basictex']):
                if not _check_dep('xelatex'):
                    output = (json.dumps({"status": "error", "message": "Missing dependency: xelatex. Install via: brew install --cask basictex"}))
                    return
        else:
            # Fallback: just check if installed
            if not _check_dep('pandoc'):
                output = (json.dumps({"status": "error", "message": "Missing dependency: pandoc. Please install manually or install Homebrew: brew install pandoc"}))
                return
            if not _check_dep('xelatex'):
                output = (json.dumps({"status": "error", "message": "Missing dependency: xelatex (MacTeX required). Please install manually."}))
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