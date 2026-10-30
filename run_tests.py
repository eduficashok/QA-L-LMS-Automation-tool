import subprocess
import sys
from pathlib import Path
root=Path(__file__).resolve().parent
commands=[['-m','unittest','test_qa','test_bb_inventory'],['regression_tests.py'],['test_qc.py']]
for args in commands:
    result=subprocess.run([sys.executable,'-B',*args],cwd=root)
    if result.returncode:
        print('FAILED:',args,flush=True);sys.exit(result.returncode)
print('All local suites passed. Live LMS acceptance is still required.',flush=True)
