"""Unit tests for build_provider / build_embedder in chancel.registry."""

from __future__ import annotations

import sys

import pytest

from chancel import registry
from chancel.embedders.hash_stub import HashStubEmbedder
from chancel.providers.echo import EchoModel


def test_default_provider_is_echo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHANCEL_PROVIDER", raising=False)

    provider = registry.build_provider()

    assert isinstance(provider, EchoModel)
    assert provider.name == "echo"


def test_unknown_provider_name_raises_and_lists_valid_names() -> None:
    with pytest.raises(ValueError) as exc_info:
        registry.build_provider("nonsense")

    message = str(exc_info.value)
    assert "nonsense" in message
    for valid in ("echo", "hostile_echo", "anthropic", "openai_compat"):
        assert valid in message


def test_env_var_selects_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHANCEL_PROVIDER", "echo")

    provider = registry.build_provider()

    assert isinstance(provider, EchoModel)


def test_explicit_name_overrides_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHANCEL_PROVIDER", "nonsense-from-env")

    provider = registry.build_provider("echo")

    assert isinstance(provider, EchoModel)


def test_hostile_echo_missing_module_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # hostile_echo is built by a different agent working the same PRP and
    # may not exist yet (or not on this branch). Setting its sys.modules
    # entry to None forces `import` to raise ImportError regardless of
    # whether the module is actually present on disk, so this test does not
    # depend on that other agent's progress.
    monkeypatch.setitem(sys.modules, "chancel.providers.hostile_echo", None)

    with pytest.raises(ValueError, match="hostile_echo"):
        registry.build_provider("hostile_echo")


def test_default_embedder_is_hash_stub() -> None:
    embedder = registry.build_embedder()

    assert isinstance(embedder, HashStubEmbedder)


def test_unknown_embedder_name_raises_and_lists_valid_names() -> None:
    with pytest.raises(ValueError) as exc_info:
        registry.build_embedder("nonsense")

    message = str(exc_info.value)
    assert "nonsense" in message
    for valid in ("hash_stub", "fastembed_local", "openai_compat"):
        assert valid in message
