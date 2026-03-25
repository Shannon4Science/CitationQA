import json
import logging
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.modules.llm_evaluator import run_llm_smoke_test


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_llm_smoke_test("hello")
    print(json.dumps(result, ensure_ascii=False, indent=2))
