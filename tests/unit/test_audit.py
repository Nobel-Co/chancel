"""Tests for the audit log module."""

from __future__ import annotations

import json
from pathlib import Path

from chancel.audit import AuditLog, _line_hash, verify_log
from chancel.model import FIRM_COLLECTION, RetrievalReceipt


def _make_receipt(
    ts: str = "2024-01-01T00:00:00Z",
    space_id: str = "test-space",
    decision: str = "allow",
    query_fingerprint: str = "abc123",
    returned_doc_ids: tuple[str, ...] = (),
) -> RetrievalReceipt:
    """Helper to create a RetrievalReceipt with fixed fields for determinism."""
    return RetrievalReceipt(
        ts=ts,
        space_id=space_id,
        decision=decision,  # type: ignore
        requested_collections=("space-test-space",),
        allowed_collections=("space-test-space",),
        reason="test reason",
        query_fingerprint=query_fingerprint,
        returned_doc_ids=returned_doc_ids,
    )


class TestAuditLogAppend:
    """Tests for AuditLog.append()."""

    def test_append_to_fresh_log(self, tmp_path: Path) -> None:
        """Append to a fresh log file creates it with correct structure."""
        log_path = tmp_path / "audit.jsonl"
        audit_log = AuditLog(log_path)

        receipt = _make_receipt()
        stored = audit_log.append(receipt)

        # Verify file exists and has one line
        assert log_path.exists()
        with open(log_path) as f:
            lines = f.readlines()
        assert len(lines) == 1

        # Verify returned receipt has genesis prev
        assert stored.prev_sha256 == "0" * 64

        # Verify stored receipt is correct
        stored_dict = json.loads(lines[0])
        assert stored_dict["prev_sha256"] == "0" * 64

    def test_three_appends_with_chain(self, tmp_path: Path) -> None:
        """Append three receipts and verify hash chain is correct."""
        log_path = tmp_path / "audit.jsonl"
        audit_log = AuditLog(log_path)

        # Append three receipts with different fingerprints
        receipt1 = _make_receipt(query_fingerprint="fp1")
        stored1 = audit_log.append(receipt1)

        receipt2 = _make_receipt(query_fingerprint="fp2")
        stored2 = audit_log.append(receipt2)

        receipt3 = _make_receipt(query_fingerprint="fp3")
        stored3 = audit_log.append(receipt3)

        # Read back and verify chain
        with open(log_path, "rb") as f:
            line1_bytes = f.readline()[:-1]  # Remove trailing newline
            line2_bytes = f.readline()[:-1]
            _ = f.readline()[:-1]  # line3, not used in manual check

        line1_hash = _line_hash(line1_bytes)
        line2_hash = _line_hash(line2_bytes)

        assert stored1.prev_sha256 == "0" * 64
        assert stored2.prev_sha256 == line1_hash
        assert stored3.prev_sha256 == line2_hash

        # Verify via verify_log
        result = verify_log(log_path)
        assert result.ok is True
        assert result.lines == 3

    def test_append_never_truncates(self, tmp_path: Path) -> None:
        """Appending to an existing log preserves prior content byte-for-byte."""
        log_path = tmp_path / "audit.jsonl"
        audit_log = AuditLog(log_path)

        # Append two receipts
        receipt1 = _make_receipt(query_fingerprint="fp1")
        audit_log.append(receipt1)

        receipt2 = _make_receipt(query_fingerprint="fp2")
        audit_log.append(receipt2)

        # Read the file
        with open(log_path, "rb") as f:
            original_bytes = f.read()

        # Append a third receipt
        receipt3 = _make_receipt(query_fingerprint="fp3")
        audit_log.append(receipt3)

        # Read again and verify original content is preserved
        with open(log_path, "rb") as f:
            new_bytes = f.read()

        assert new_bytes[: len(original_bytes)] == original_bytes


class TestVerifyLog:
    """Tests for verify_log()."""

    def test_verify_empty_file(self, tmp_path: Path) -> None:
        """Verifying an empty file returns ok with lines=0."""
        log_path = tmp_path / "empty.jsonl"
        log_path.touch()

        result = verify_log(log_path)
        assert result.ok is True
        assert result.lines == 0
        assert result.first_bad_line is None
        assert result.reason is None

    def test_verify_missing_file(self, tmp_path: Path) -> None:
        """Verifying a nonexistent file returns ok with lines=0."""
        log_path = tmp_path / "missing.jsonl"

        result = verify_log(log_path)
        assert result.ok is True
        assert result.lines == 0

    def test_mutation_in_middle_line_caught_by_chain(self, tmp_path: Path) -> None:
        """Mutating a value in a middle line is caught by hash chain on next line.

        When line 2's value is mutated, its canonical_json bytes change. This causes
        line 3's stored prev_sha256 (which points to line 2's original hash) to no
        longer match the recomputed hash of mutated line 2. The chain check catches
        this at line 3, not at line 2.
        """
        log_path = tmp_path / "audit.jsonl"
        audit_log = AuditLog(log_path)

        # Append three receipts
        receipt1 = _make_receipt(query_fingerprint="fp1")
        audit_log.append(receipt1)

        receipt2 = _make_receipt(query_fingerprint="fp2")
        audit_log.append(receipt2)

        receipt3 = _make_receipt(query_fingerprint="fp3")
        audit_log.append(receipt3)

        # Mutate line 2 at the binary level: change fp2 to fp9
        with open(log_path, "rb") as f:
            content = f.read()

        lines = content.split(b"\n")
        lines[1] = lines[1].replace(b"fp2", b"fp9")
        mutated_content = b"\n".join(lines)

        with open(log_path, "wb") as f:
            f.write(mutated_content)

        # Verify should fail at line 3 with hash chain broken
        result = verify_log(log_path)
        assert result.ok is False
        assert result.first_bad_line == 3
        assert result.reason == "hash chain broken"

    def test_mutation_in_final_line_is_not_detected(self, tmp_path: Path) -> None:
        """Mutating the final line is not detected.

        The hash chain cannot catch the final line (nothing points to it), and
        re-serialization of the mutated value matches the mutated bytes, so the
        canonical check also passes. This is a real limitation of hash chains:
        the last entry needs an external anchor to detect value tampering.
        """
        log_path = tmp_path / "audit.jsonl"
        audit_log = AuditLog(log_path)

        # Append three receipts
        receipt1 = _make_receipt(query_fingerprint="fp1")
        audit_log.append(receipt1)

        receipt2 = _make_receipt(query_fingerprint="fp2")
        audit_log.append(receipt2)

        receipt3 = _make_receipt(query_fingerprint="fp3")
        audit_log.append(receipt3)

        # Mutate line 3 at the binary level: change fp3 to fp9
        with open(log_path, "rb") as f:
            content = f.read()

        lines = content.split(b"\n")
        lines[2] = lines[2].replace(b"fp3", b"fp9")
        mutated_content = b"\n".join(lines)

        with open(log_path, "wb") as f:
            f.write(mutated_content)

        # Verify should still pass (the limitation)
        result = verify_log(log_path)
        assert result.ok is True
        assert result.lines == 3

    def test_tamper_with_prev_sha256(self, tmp_path: Path) -> None:
        """Tampering with a prev_sha256 field breaks the chain at that line."""
        log_path = tmp_path / "audit.jsonl"
        audit_log = AuditLog(log_path)

        # Append three receipts
        receipt1 = _make_receipt(query_fingerprint="fp1")
        audit_log.append(receipt1)

        receipt2 = _make_receipt(query_fingerprint="fp2")
        audit_log.append(receipt2)

        receipt3 = _make_receipt(query_fingerprint="fp3")
        audit_log.append(receipt3)

        # Tamper with line 2's prev_sha256 by replacing a character in it
        with open(log_path, "rb") as f:
            content = f.read()

        lines = content.split(b"\n")
        # Find and replace the first hex digit in prev_sha256 with a different one
        # The format is: "prev_sha256":"<hexdigit><hexdigits..."
        line2_modified = lines[1]
        # Find the prev_sha256 field and replace one character
        prev_sha_prefix = b'"prev_sha256":"'
        idx = line2_modified.find(prev_sha_prefix)
        if idx != -1:
            # Replace the first hex digit after the quote
            start = idx + len(prev_sha_prefix)
            # Replace 'a' with 'f' or vice versa to ensure change
            old_char = line2_modified[start : start + 1]
            new_char = b"f" if old_char != b"f" else b"a"
            line2_modified = line2_modified[:start] + new_char + line2_modified[start + 1 :]
        lines[1] = line2_modified
        mutated_content = b"\n".join(lines)

        with open(log_path, "wb") as f:
            f.write(mutated_content)

        # Verify should fail at line 2
        result = verify_log(log_path)
        assert result.ok is False
        assert result.first_bad_line == 2
        assert result.reason == "hash chain broken"

    def test_invalid_json_in_line(self, tmp_path: Path) -> None:
        """Malformed JSON in a line is caught."""
        log_path = tmp_path / "audit.jsonl"
        audit_log = AuditLog(log_path)

        receipt1 = _make_receipt(query_fingerprint="fp1")
        audit_log.append(receipt1)

        # Append invalid JSON
        with open(log_path, "a") as f:
            f.write("{ invalid json\n")

        result = verify_log(log_path)
        assert result.ok is False
        assert result.first_bad_line == 2
        assert result.reason == "invalid receipt"

    def test_invalid_receipt_in_valid_json(self, tmp_path: Path) -> None:
        """Valid JSON that doesn't deserialize to RetrievalReceipt is caught."""
        log_path = tmp_path / "audit.jsonl"
        audit_log = AuditLog(log_path)

        receipt1 = _make_receipt(query_fingerprint="fp1")
        audit_log.append(receipt1)

        # Append valid JSON but invalid receipt (missing required fields)
        with open(log_path, "a") as f:
            f.write('{"ts":"2024-01-01T00:00:00Z"}\n')

        result = verify_log(log_path)
        assert result.ok is False
        assert result.first_bad_line == 2
        assert result.reason == "invalid receipt"

    def test_cross_scope_receipt_detected(self, tmp_path: Path) -> None:
        """A receipt claiming collections outside its space is flagged."""
        log_path = tmp_path / "audit.jsonl"

        # Create a receipt with cross-scope collections
        # We need to bypass AuditLog to write a cross-scope receipt
        receipt = RetrievalReceipt(
            ts="2024-01-01T00:00:00Z",
            space_id="test-space",
            decision="allow",  # type: ignore
            requested_collections=("space-test-space",),
            allowed_collections=("space-other-space",),  # Cross-scope!
            reason="test",
            query_fingerprint="abc123",
            returned_doc_ids=(),
            prev_sha256="0" * 64,
        )

        # Write it directly to the file, bypassing AuditLog's logic
        with open(log_path, "w") as f:
            f.write(receipt.canonical_json() + "\n")

        result = verify_log(log_path)
        assert result.ok is False
        assert result.first_bad_line == 1
        assert result.reason == "receipt names a collection outside its scope"

    def test_firm_collection_is_allowed(self, tmp_path: Path) -> None:
        """FIRM_COLLECTION is allowed in allowed_collections for any space."""
        log_path = tmp_path / "audit.jsonl"
        audit_log = AuditLog(log_path)

        # Create a receipt with FIRM_COLLECTION in allowed_collections
        receipt = RetrievalReceipt(
            ts="2024-01-01T00:00:00Z",
            space_id="test-space",
            decision="allow",  # type: ignore
            requested_collections=(FIRM_COLLECTION,),
            allowed_collections=(FIRM_COLLECTION, "space-test-space"),
            reason="test",
            query_fingerprint="abc123",
            returned_doc_ids=(),
        )

        audit_log.append(receipt)

        result = verify_log(log_path)
        assert result.ok is True
        assert result.lines == 1
