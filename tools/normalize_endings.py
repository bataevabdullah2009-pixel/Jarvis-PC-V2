import os

def normalize_files():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    print(f"Normalizing line endings starting from root: {root_dir}")

    exclude_dirs = {
        ".git", "node_modules", "_archive", "build", "dist",
        "release", "app_current", ".venv", "venv", "__pycache__"
    }

    lf_extensions = {".py", ".ts", ".tsx", ".js", ".json", ".md", ".css", ".html"}
    crlf_extensions = {".ps1", ".bat"}
    
    normalized_count = 0
    unchanged_count = 0

    for root, dirs, files in os.walk(root_dir):
        # In-place modification to avoid scanning excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, root_dir)
            ext = os.path.splitext(file)[1].lower()

            is_lf = ext in lf_extensions
            is_crlf = ext in crlf_extensions

            if not (is_lf or is_crlf):
                continue

            try:
                with open(file_path, "rb") as f:
                    original_bytes = f.read()

                # Step 1: Normalize all line endings (CRLF, isolated CR) to clean LF (\n)
                # First convert CRLF to LF
                temp_bytes = original_bytes.replace(b"\r\n", b"\n")
                # Then convert any leftover CR-only (\r) to LF (\n)
                lf_bytes = temp_bytes.replace(b"\r", b"\n")

                # Step 2: If the file is a CRLF file, convert clean LF (\n) to CRLF (\r\n)
                if is_crlf:
                    target_bytes = lf_bytes.replace(b"\n", b"\r\n")
                else:
                    target_bytes = lf_bytes

                # Step 3: Write back if changed
                if target_bytes != original_bytes:
                    # Determine line endings before/after for logging
                    orig_lf = original_bytes.count(b"\n")
                    orig_cr = original_bytes.count(b"\r")
                    orig_crlf = original_bytes.count(b"\r\n")
                    orig_isolated = orig_cr - orig_crlf

                    new_lf = target_bytes.count(b"\n")
                    new_cr = target_bytes.count(b"\r")
                    new_crlf = target_bytes.count(b"\r\n")
                    new_isolated = new_cr - new_crlf

                    print(f"Normalized: {rel_path}")
                    print(f"  Before: LF={orig_lf}, CR={orig_cr} (isolated={orig_isolated})")
                    print(f"  After:  LF={new_lf}, CR={new_cr} (isolated={new_isolated})")

                    with open(file_path, "wb") as f:
                        f.write(target_bytes)
                    normalized_count += 1
                else:
                    unchanged_count += 1

            except Exception as e:
                print(f"Error processing {rel_path}: {e}")

    print(f"\nNormalization complete. Normalized: {normalized_count}, Unchanged: {unchanged_count}")

if __name__ == "__main__":
    normalize_files()
