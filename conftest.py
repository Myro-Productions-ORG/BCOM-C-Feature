# conftest.py — project root
# Ensures src/ is on sys.path before tests/ so that `import orchestrator`
# resolves to src/orchestrator, not tests/orchestrator.
# Required because pytest (prepend/importlib mode) may otherwise shadow src packages.
import sys
from pathlib import Path

_src = str(Path(__file__).parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
