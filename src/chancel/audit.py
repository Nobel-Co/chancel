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


def _last_line(content: bytes) -> bytes:
    """The final newline-delimited line of ``content``, without its trailing
    LF. A single trailing newline is expected (the log ends every line with
    one); empty content yields ``b""``."""
    lines = content.split(b"\n")
    if lines and lines[-1] == b"":
        lines = lines[:-1]
    return lines[-1] if lines else b""


def head_line_hash(path: Path) -> str | None:
    """SHA-256 of the log's last non-empty line, or ``None`` for a missing or
    empty log.

    This is the anchor a user records out of band: the hash chain binds every
    line to its predecessor but nothing points at the final line, so a mutated
    last line is only detectable by comparing against a value recorded earlier.
    """
    if not path.exists() or path.stat().st_size == 0:
        return None
    last = _last_line(path.read_bytes())
    return _line_hash(last) if last else None


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
        # A first line anchors the chain at all-zeroes; every later line is
        # bound to the hash of the one before it.
        prev_sha256 = head_line_hash(self.path) or "0" * 64
        stored_receipt = receipt.model_copy(update={"prev_sha256": prev_sha256})

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
