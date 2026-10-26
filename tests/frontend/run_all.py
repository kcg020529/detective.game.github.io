import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
checks = ["check_flow.py", "check_errors.py", "check_http.py", "check_roles.py", "check_split.py"]
results = []

for check in checks:
    result = subprocess.run([sys.executable, str(HERE / check)], cwd=ROOT)
    results.append((check, result.returncode))

print("\nSummary:")
for name, code in results:
    print(f"{'PASS' if code == 0 else 'FAIL'} {name}")
sys.exit(any(code != 0 for _, code in results))
