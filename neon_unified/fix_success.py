with open("C:/Users/Admin/Downloads/neon_unified/generation_core.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find and replace the success logic
old_logic = """        hard = [e for e in result.errors if not e.startswith("[soft]")]
        if test_result.ran:
            result.success = len(hard) == 0 and test_result.passed
        else:
            result.success = len(hard) == 0 and len(result.files_generated) >= 4"""

new_logic = """        hard = [e for e in result.errors if not e.startswith("[soft]")]
        # success = (no hard errors) AND (tests actually ran AND passed)
        # if tests never ran -> success=False
        # soft UI errors are warnings only (not in hard)
        if test_result.ran:
            result.success = len(hard) == 0 and test_result.passed
        else:
            result.success = False"""

if old_logic in content:
    content = content.replace(old_logic, new_logic)
    with open("C:/Users/Admin/Downloads/neon_unified/generation_core.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("SUCCESS: success logic updated")
else:
    print("ERROR: Could not find old logic")
