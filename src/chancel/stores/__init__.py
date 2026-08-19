"""Vector store backends (Layer A) and storage layouts (Layer B).

Nothing in this package is imported at ``chancel`` top-level import time
except the base protocols and the three pure-Python layouts + the in-memory
reference store; ``chancel.stores.qdrant`` is imported lazily by
``chancel.registry.build_store`` so a base install never needs qdrant-client.
"""

from __future__ import annotations
