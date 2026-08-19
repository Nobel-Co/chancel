"""ChatModel adapters: neutral types in ``base``, one module per provider.

Every provider-specific field name, wire format, and SDK import lives below
this package boundary. Nothing above it (``chancel.agent``, ``chancel.retriever``,
``chancel.policy``, ``chancel.model``) may name a concrete provider -- a CI grep
enforces this over ``src/chancel``, excluding this package, ``embedders/``, and
``registry.py``.
"""

from __future__ import annotations
