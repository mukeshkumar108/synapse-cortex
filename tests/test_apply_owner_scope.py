"""Scoped apply: world-scoped owners (RPD2 per-chat worlds) can apply consolidation while every other owner stays untouched."""
from src.services.session_apply import apply_enabled


def test_apply_is_off_by_default(monkeypatch):
    monkeypatch.delenv("SESSION_CONSOLIDATION_APPLY", raising=False)
    monkeypatch.delenv("SESSION_CONSOLIDATION_APPLY_OWNER_PREFIXES", raising=False)
    assert apply_enabled() is False and apply_enabled("world:rpd2:u:c:chat") is False and apply_enabled("user_abc") is False


def test_owner_prefix_enables_only_matching_owners(monkeypatch):
    monkeypatch.delenv("SESSION_CONSOLIDATION_APPLY", raising=False)
    monkeypatch.setenv("SESSION_CONSOLIDATION_APPLY_OWNER_PREFIXES", "world:")
    assert apply_enabled("world:rpd2:u1:audrey-vale:chatA") is True
    assert apply_enabled("user_5377a025") is False             # a real person's world is never touched by the scoped switch
    assert apply_enabled() is False and apply_enabled(None) is False


def test_the_global_switch_still_enables_everyone(monkeypatch):
    monkeypatch.setenv("SESSION_CONSOLIDATION_APPLY", "1")
    assert apply_enabled() is True and apply_enabled("user_abc") is True


def test_multiple_prefixes_and_whitespace(monkeypatch):
    monkeypatch.delenv("SESSION_CONSOLIDATION_APPLY", raising=False)
    monkeypatch.setenv("SESSION_CONSOLIDATION_APPLY_OWNER_PREFIXES", " world: , sandbox_ ")
    assert apply_enabled("sandbox_test") is True and apply_enabled("world:x") is True and apply_enabled("user_x") is False
