"""Unit tests for build_provider / build_embedder in chancel.registry."""

from __future__ import annotations

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


def test_hostile_echo_provider_builds() -> None:
    from chancel.providers.hostile_echo import HostileEchoModel

    provider = registry.build_provider("hostile_echo")

    assert isinstance(provider, HostileEchoModel)
    assert provider.name == "hostile_echo"


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
