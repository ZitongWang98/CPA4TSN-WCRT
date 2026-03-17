"""Run all config optimizer tests."""
import subprocess, sys, os

DIR = os.path.dirname(os.path.abspath(__file__))
tests = [
    'test_config.py',
    'test_config_extended.py',
    'test_layer1.py',
    'test_layer2.py',
    'test_layer3.py',
    'test_layer4_misc.py',
    'test_integration.py',
]

failed = []
for t in tests:
    print('\n' + '=' * 60)
    print('Running %s' % t)
    print('=' * 60)
    rc = subprocess.call([sys.executable, os.path.join(DIR, t)])
    if rc != 0:
        failed.append(t)

print('\n' + '=' * 60)
if failed:
    print('FAILED: %s' % ', '.join(failed))
else:
    print('ALL %d test files PASSED' % len(tests))
print('=' * 60)
sys.exit(1 if failed else 0)
