"""Confirms importing the reference-layout stack never pulls in qdrant_client.

Base install viability: `pip install chancel` (no [qdrant] extra) must be
able to import every non-qdrant module in this package. qdrant_client's
import is guarded inside chancel.stores.qdrant specifically so this holds.
Run in a subprocess so an earlier test file that legitimately imports
qdrant_client (tests/integration/test_qdrant_store.py) can't pollute this
process's sys.modules and produce a false negative.
"""

from __future__ import annotations

import subprocess
import sys

_CHECK_SCRIPT = """
import sys
import chancel
import chancel.stores.inmemory
import chancel.stores.isolated
import chancel.stores.filtered
import chancel.stores.shared
import chancel.retriever
import chancel.ingest
import chancel.registry
assert "qdrant_client" not in sys.modules, sorted(sys.modules)
print("OK")
"""


def test_importing_inmemory_stack_never_imports_qdrant_client() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _CHECK_SCRIPT], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
