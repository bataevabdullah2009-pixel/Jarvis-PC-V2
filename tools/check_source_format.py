#!/usr/bin/env python3
import os
import sys
import py_compile

def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    print(f"Scanning codebase for formatting issues starting from root: {root_dir}")

    # Exclude directories
    exclude_dirs = {
        ".git", "node_modules", "_archive", "build", "dist",
        "release", "app_current", ".venv", "venv", "__pycache__"
    }

    errors = []

    # Check .gitattributes
    gitattributes_path = os.path.join(root_dir, ".gitattributes")
    if os.path.exists(gitattributes_path):
        try:
            with open(gitattributes_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f]
            if "* text=auto" not in lines:
                errors.append(f".gitattributes: does not contain a separate line '* text=auto'")
        except Exception as e:
            errors.append(f".gitattributes: failed to read/validate: {e}")
    else:
        errors.append(".gitattributes: file is missing!")

    # Walk directory tree
    for root, dirs, files in os.walk(root_dir):
        # Modify dirs in-place to avoid scanning excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, root_dir)
            ext = os.path.splitext(file)[1].lower()

            target_lf_exts = {".py", ".ts", ".tsx", ".js", ".json", ".md", ".css", ".html"}
            target_crlf_exts = {".ps1", ".bat"}

            # Byte-level line endings verification
            if ext in target_lf_exts or ext in target_crlf_exts:
                try:
                    with open(file_path, "rb") as f:
                        content = f.read()
                    
                    lf_count = content.count(b"\n")
                    cr_count = content.count(b"\r")
                    crlf_count = content.count(b"\r\n")

                    # CR-only line endings check (isolated \r)
                    has_isolated_cr = b"\r" in content.replace(b"\r\n", b"")

                    if lf_count == 0:
                        errors.append(f"Format: {rel_path} has LF count == 0")
                    
                    if has_isolated_cr:
                        errors.append(f"Format: {rel_path} CR-only line endings detected")
                except Exception as e:
                    errors.append(f"Format: {rel_path} failed line endings check: {e}")

            # Python files compile check
            if ext == ".py":
                try:
                    py_compile.compile(file_path, doraise=True)
                except py_compile.PyCompileError as e:
                    errors.append(f"Python: {rel_path} fails compilation: {e.msg}")
                except Exception as e:
                    errors.append(f"Python: {rel_path} fails to compile: {e}")

            # PowerShell check
            elif ext == ".ps1":
                try:
                    size = os.path.getsize(file_path)
                    if size > 2048:  # > 2 KB
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            lines = f.readlines()
                        # Normalize lines (ignoring blank lines/comments if needed, but a single line is a single line)
                        # Remove empty ending elements
                        lines = [line for line in lines if line.strip()]
                        if len(lines) <= 1:
                            errors.append(f"PowerShell: {rel_path} is larger than 2KB ({size} bytes) but contains only {len(lines)} line(s)")
                except Exception as e:
                    errors.append(f"PowerShell: {rel_path} failed to read: {e}")

            # Batch check
            elif ext == ".bat":
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = [line for line in f if line.strip()]
                    if len(lines) <= 1:
                        errors.append(f"Batch: {rel_path} has only {len(lines)} line(s)")
                except Exception as e:
                    errors.append(f"Batch: {rel_path} failed to read: {e}")

            # TS / TSX check
            elif ext in {".ts", ".tsx"}:
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        first_line = f.readline()
                    if len(first_line) > 2000:
                        errors.append(f"TypeScript: {rel_path} has a first line longer than 2000 characters ({len(first_line)} chars)")
                except Exception as e:
                    errors.append(f"TypeScript: {rel_path} failed to read: {e}")

    # Output results
    if errors:
        print("\n[!] FORMATTING AND COMPILATION ERRORS DETECTED:")
        for error in errors:
            print(f"  - {error}")
        print(f"\nTotal violations: {len(errors)}")
        sys.exit(1)
    else:
        print("\n[+] SUCCESS: No formatting or compilation errors detected in the codebase.")
        sys.exit(0)

if __name__ == "__main__":
    main()
