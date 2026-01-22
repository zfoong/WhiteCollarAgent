#!/usr/bin/with-contenv bash

# ---------------------------------------------------------------------
# PURE PYTHON INSTALLATION SCRIPT
#
# Based on testing, running 'apt-get' in this container breaks the
# delicate KasmVNC input hooks.
# We install ONLY the Python packages using pip.
# ---------------------------------------------------------------------

echo "=================================================="
echo " [Custom Init] Running PURE-PYTHON install... "
echo "=================================================="

# Install python libraries into the existing environment.
# This mimics running "pip install pyautogui" manually in the terminal.
pip3 install \
    --no-cache-dir \
    --break-system-packages \
    pyautogui \
    Pillow

echo "=================================================="
echo " [Custom Init] Finished. Basic automation ready. "
echo "=================================================="