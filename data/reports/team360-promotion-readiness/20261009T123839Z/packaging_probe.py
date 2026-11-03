"""Validation-only wheel inventory and isolated entrypoint import; no runtime fixes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import site
import tempfile
import zipfile

output = Path(__file__).resolve().parent / 'packaging'
wheel = next(output.glob('*.whl'))
with zipfile.ZipFile(wheel) as archive:
    names = archive.namelist()
expected = ['ls_iMotorSoft_Srv05.py', 'ls_iMotorSoft_Srv01.py', 'globalVar.py',
            'modules/srv05_architecture.py', 'modules/srv05_runtime.py']
with tempfile.TemporaryDirectory(prefix='srv05-wheel-probe-') as cwd:
    child = subprocess.run([sys.executable, '-I', '-S', '-c',
        'import sys; sys.path[:0] = sys.argv[1:]; import ls_iMotorSoft_Srv05',
        str(wheel), *site.getsitepackages()], cwd=cwd, capture_output=True, text=True, timeout=15)
result = {'command': 'python -I -S -c <wheel-only entrypoint import> <wheel> <dependency site-packages without .pth>',
          'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(),
          'members': len(names), 'expected_members': {n: n in names for n in expected},
          'isolated_import_returncode': child.returncode,
          'isolated_import_stderr': child.stderr,
          'classification': 'DEFECT' if child.returncode or not all(n in names for n in expected) else 'READY',
          'promotion_impact': 'BLOCKING_FOR_PROMOTION' if child.returncode or not all(n in names for n in expected) else 'NON_BLOCKING_FOR_PROMOTION',
          'harness_note': 'Initial -I-only attempt resolved editable source through site .pth and was invalid evidence. -S disables .pth processing; dependency paths added explicitly.',
          'reason': 'Wheel build success does not demonstrate ASGI entrypoint inclusion.',
          'temporary_directory_cleanup': True}
(output / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
