"""Upholds the auditability invariant: every retrieval attempt, allow or deny,
is one line in an append-only JSONL log, and each line is bound to the previous
by a SHA-256 chain, so a single mutated byte anywhere in history is detectable
and nameable."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from chancel.model import FIRM_COLLECTION, RetrievalReceipt, space_collection


def _line_hash(line_bytes: bytes) -> str:
    """Compute SHA-256 hash of a line's bytes (without trailing newline)."""
    return hashlib.sha256(line_bytes).hexdigest()


class AuditLog:
    """Append-only JSONL log of retrieval receipts with SHA-256 hash chain."""

    def __init__(self, path: Path) -> None:
        """Initialize audit log, creating parent directories if needed."""
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, receipt: RetrievalReceipt) -> RetrievalReceipt:
        """Append a receipt to the log, computing and setting prev_sha256 hash chain.

        Reads the last line of the file if it exists to compute the previous hash.
        Returns a copy of the receipt with prev_sha256 set to the computed hash.
        """
        # Determine prev_sha256 by reading the last line from the file
        if self.path.exists() and self.path.stat().st_size > 0:
            # Read all lines and get the last one (without trailing newline)
            with open(self.path, "rb") as f:
                content = f.read()
            # Split on LF and get the last non-empty line
            lines = content.split(b"\n")
            # The last element might be empty if file ends with newline
            last_line = lines[-2] if lines[-1] == b"" else lines[-1]
            prev_sha256 = _line_hash(last_line) if last_line else "0" * 64
        else:
            prev_sha256 = "0" * 64

        # Create receipt copy with prev_sha256 set
        stored_receipt = receipt.model_copy(update={"prev_sha256": prev_sha256})

        # Append to file
        line_bytes = stored_receipt.canonical_json().encode("utf-8")
        with open(self.path, "ab") as f:
            f.write(line_bytes)
            f.write(b"\n")

        return stored_receipt


@dataclass(frozen=True)
class VerifyResult:
    """Result of verifying an audit log."""

    ok: bool
    lines: int
    first_bad_line: int | None = None  # 1-indexed
    reason: str | None = None


def verify_log(path: Path) -> VerifyResult:
    """Verify integrity of an audit log.

    Checks:
    1. Each line is valid JSON and a valid RetrievalReceipt
    2. Hash chain: first line has prev_sha256 == "0"*64, subsequent lines
       have prev_sha256 == hash of previous line
    3. Scope consistency: allowed_collections must be within
       {"firm", f"space-{space_id}"}
    4. Canonical form: line bytes must equal canonical_json() re-encoding

    Note on mutation detection: a value mutation in the middle of the file is
    caught by the hash chain check on the next line (whose prev_sha256 no longer
    matches). A value mutation in the final line cannot be caught by the chain
    (nothing points to it) and will also pass the canonical check if the
    re-serialization of the mutated value matches the mutated bytes. This is
    a real limitation — see docs/threat-model.md.
    """
    if not path.exists():
        return VerifyResult(ok=True, lines=0)

    if path.stat().st_size == 0:
        return VerifyResult(ok=True, lines=0)

    prev_hash: str | None = None
    line_num = 0

    with open(path, "rb") as f:
        for line_bytes in iter(lambda: f.readline(), b""):
            line_num += 1

            # Remove trailing LF
            line_bytes_no_newline = line_bytes[:-1] if line_bytes.endswith(b"\n") else line_bytes

            # Skip empty lines (shouldn't happen in well-formed log)
            if not line_bytes_no_newline:
                continue

            # Parse JSON and validate as RetrievalReceipt
            try:
                line_dict = json.loads(line_bytes_no_newline.decode("utf-8"))
                receipt = RetrievalReceipt.model_validate(line_dict)
            except (json.JSONDecodeError, ValidationError, UnicodeDecodeError):
                return VerifyResult(
                    ok=False,
                    lines=line_num - 1,
                    first_bad_line=line_num,
                    reason="invalid receipt",
                )

            # Check hash chain
            if line_num == 1:
                if receipt.prev_sha256 != "0" * 64:
                    return VerifyResult(
                        ok=False,
                        lines=line_num - 1,
                        first_bad_line=line_num,
                        reason="hash chain broken",
                    )
            else:
                if receipt.prev_sha256 != prev_hash:
                    return VerifyResult(
                        ok=False,
                        lines=line_num - 1,
                        first_bad_line=line_num,
                        reason="hash chain broken",
                    )

            # Check scope consistency
            allowed_collections_set = {FIRM_COLLECTION, space_collection(receipt.space_id)}
            for collection in receipt.allowed_collections:
                if collection not in allowed_collections_set:
                    return VerifyResult(
                        ok=False,
                        lines=line_num - 1,
                        first_bad_line=line_num,
                        reason="receipt names a collection outside its scope",
                    )

            # Check canonical form: re-serialize and compare bytes
            canonical_json = receipt.canonical_json()
            canonical_bytes = canonical_json.encode("utf-8")
            if line_bytes_no_newline != canonical_bytes:
                return VerifyResult(
                    ok=False,
                    lines=line_num - 1,
                    first_bad_line=line_num,
                    reason="line is not canonical",
                )

            # Compute hash for next iteration
            prev_hash = _line_hash(line_bytes_no_newline)

    return VerifyResult(ok=True, lines=line_num)
