"""
Run this once from your backend/ directory:
    python3 fix_test_api_routes.py

Removes the local `client` fixture from tests/test_api_routes.py (it now
lives in conftest.py, shared across all test files) — a local fixture of
the same name always shadows conftest.py's version for that file's own
tests, which is exactly what was silently bypassing auth.
"""
import re

path = "tests/test_api_routes.py"

with open(path) as f:
    content = f.read()

pattern = re.compile(
    r'@pytest\.fixture\ndef client\(\):.*?app\.dependency_overrides\.clear\(\)\n\n\n',
    re.DOTALL
)
new_content, count = pattern.subn(
    '# client fixture now lives in conftest.py (shared across test files) —\n'
    '# removed from here so this file uses that shared version instead of\n'
    '# shadowing it with its own auth-unaware copy.\n\n\n',
    content
)

if count != 1:
    print(f"WARNING: expected exactly 1 replacement, made {count}. "
          f"Check the file manually — the fixture may not have matched "
          f"the expected pattern exactly.")
else:
    with open(path, 'w') as f:
        f.write(new_content)
    print("Fixture removed successfully.")
