"""Tests for the settings accessor, ``llm_audit.conf.audit_settings`` (M6).

The accessor (CLAUDE.md §8) is the one place plugin code reads pipeline-wide configuration.
Its contract is small and worth pinning down: a configured value wins, an absent one falls
back to the documented default, and an unknown key fails loudly rather than silently
returning ``None``. (The richer ``resolve_backend_config`` is covered in ``test_backends``.)
"""

import pytest
from django.test import override_settings

from llm_audit.conf import DEFAULTS, audit_settings


def test_returns_default_when_setting_absent():
    # tests/settings.py defines LLM_AUDIT without MAX_TOKENS/DEFAULT_RECORD_LIMIT, so these
    # exercise the defaults path.
    assert audit_settings.MAX_TOKENS == DEFAULTS["MAX_TOKENS"] == 1024
    assert audit_settings.DEFAULT_RECORD_LIMIT == DEFAULTS["DEFAULT_RECORD_LIMIT"] == 50
    assert audit_settings.CHUNK_TOKEN_THRESHOLD == DEFAULTS["CHUNK_TOKEN_THRESHOLD"] == 3000


@override_settings(LLM_AUDIT={"MAX_TOKENS": 4096})
def test_user_value_overrides_default():
    assert audit_settings.MAX_TOKENS == 4096


def test_unknown_setting_raises_attribute_error():
    # A typo'd or unsupported key must fail loudly, not silently return None — the accessor
    # doubles as documentation of what is configurable.
    with pytest.raises(AttributeError, match="Invalid LLM_AUDIT setting"):
        _ = audit_settings.NOT_A_REAL_SETTING


@override_settings()
def test_missing_llm_audit_dict_falls_back_to_defaults(settings):
    # If a project never defines LLM_AUDIT at all, the accessor still serves defaults.
    del settings.LLM_AUDIT
    assert audit_settings.MODEL == DEFAULTS["MODEL"]
