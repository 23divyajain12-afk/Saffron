import importlib, traceback

try:
    importlib.import_module('ui')
    print('ui imported OK')
except Exception:
    traceback.print_exc()
