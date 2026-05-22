from __future__ import annotations

import os
import sys
import subprocess

def test_source_format_guard() -> None:
    """Asserts that tools/check_source_format.py executes and passes successfully."""
    # Resolve project root relative to this test file
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    script_path = os.path.join(project_root, "tools", "check_source_format.py")
    
    # Run the validation script
    res = subprocess.run(
        [sys.executable, script_path],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    
    assert res.returncode == 0, (
        f"Source formatting check failed (exit code {res.returncode}):\n"
        f"STDOUT:\n{res.stdout}\n"
        f"STDERR:\n{res.stderr}"
    )
