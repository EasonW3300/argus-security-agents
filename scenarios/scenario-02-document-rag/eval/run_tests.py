from __future__ import annotations

import importlib.util
import inspect
import sys
import tempfile
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _call_test(function):
    signature = inspect.signature(function)
    kwargs = {}
    with tempfile.TemporaryDirectory() as directory:
        for name in signature.parameters:
            if name == "tmp_path":
                kwargs[name] = Path(directory)
            else:
                raise TypeError("unsupported fixture: %s" % name)
        function(**kwargs)


def main() -> int:
    sys.path.insert(0, str(ROOT))
    failures = []
    total = 0
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        try:
            module = _load_module(path)
        except Exception:
            failures.append((str(path), "module import", traceback.format_exc()))
            continue
        for name, function in inspect.getmembers(module, inspect.isfunction):
            if not name.startswith("test_"):
                continue
            total += 1
            try:
                _call_test(function)
            except Exception:
                failures.append((str(path), name, traceback.format_exc()))

    for path, name, detail in failures:
        print("FAIL %s::%s" % (path, name))
        print(detail)
    print("%d tests, %d failures" % (total, len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

