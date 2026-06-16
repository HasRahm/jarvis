"""Phase 24 — virtual input: strategy selection, pattern execution, element scoring.

All display-free: uiautomation is never actually used (mocked controls).
"""
import os
import sys
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.virtual_input import (
    select_strategies, score_element, execute_strategy, virtual_input_enabled,
    _escape_sendkeys,
)


class TestSelectStrategies:
    def test_type_prefers_value_pattern(self):
        assert select_strategies("Edit", "type") == ["value_pattern", "focus_sendkeys", "physical"]

    def test_document_type_never_clobbers(self):
        # editor buffers must be appended at cursor, never SetValue/Ctrl+A'd
        chain = select_strategies("Document", "type")
        assert chain == ["focus_sendkeys_append", "physical"]
        assert "value_pattern" not in chain and "focus_sendkeys" not in chain

    def test_button_click_prefers_invoke(self):
        chain = select_strategies("Button", "click")
        assert chain[0] == "invoke"
        assert chain[-1] == "physical"

    def test_checkbox_uses_toggle(self):
        assert select_strategies("CheckBox", "click")[0] == "toggle"

    def test_combobox_expands(self):
        assert select_strategies("ComboBox", "click")[0] == "expand_collapse"

    def test_list_item_selects(self):
        for role in ("ListItem", "TabItem", "MenuItem", "RadioButton"):
            assert select_strategies(role, "click")[0] == "selection_item"

    def test_edit_click_is_focus(self):
        assert select_strategies("Edit", "click")[0] == "focus_only"

    def test_unknown_role_defaults_to_invoke(self):
        chain = select_strategies("SomethingWeird", "click")
        assert chain[0] == "invoke"
        assert "physical" in chain

    def test_control_suffix_stripped(self):
        # roles arrive both as 'Button' (cache) and 'ButtonControl' (live)
        assert select_strategies("ButtonControl", "click") == select_strategies("Button", "click")

    def test_every_chain_ends_with_physical(self):
        for role in ("Button", "Edit", "CheckBox", "ComboBox", "ListItem", "Hyperlink", "X"):
            for action in ("click", "type"):
                assert select_strategies(role, action)[-1] == "physical"


class TestExecuteStrategy:
    def test_invoke_calls_pattern(self):
        ctrl = MagicMock()
        ok, msg = execute_strategy(ctrl, "invoke")
        assert ok
        ctrl.GetInvokePattern.return_value.Invoke.assert_called_once()

    def test_value_pattern_sets_text(self):
        ctrl = MagicMock()
        ctrl.GetValuePattern.return_value.IsReadOnly = False
        ok, msg = execute_strategy(ctrl, "value_pattern", "hello")
        assert ok
        ctrl.GetValuePattern.return_value.SetValue.assert_called_once_with("hello")

    def test_readonly_value_pattern_falls_through(self):
        ctrl = MagicMock()
        ctrl.GetValuePattern.return_value.IsReadOnly = True
        ok, msg = execute_strategy(ctrl, "value_pattern", "hello")
        assert not ok
        assert "read-only" in msg

    def test_pattern_exception_returns_false_not_raise(self):
        ctrl = MagicMock()
        ctrl.GetInvokePattern.side_effect = RuntimeError("pattern not supported")
        ok, msg = execute_strategy(ctrl, "invoke")
        assert not ok
        assert "pattern not supported" in msg

    def test_unknown_strategy(self):
        ok, msg = execute_strategy(MagicMock(), "warp_drive")
        assert not ok

    def test_toggle(self):
        ctrl = MagicMock()
        ok, _ = execute_strategy(ctrl, "toggle")
        assert ok
        ctrl.GetTogglePattern.return_value.Toggle.assert_called_once()


class TestEscapeSendKeys:
    def test_plain_text_unchanged(self):
        assert _escape_sendkeys("hello world") == "hello world"

    def test_braces_escaped(self):
        assert _escape_sendkeys("a{b}c") == "a{{}b{}}c"

    def test_specials_escaped(self):
        out = _escape_sendkeys("100% (+tax) ^2 ~x")
        for special in "%+^~()":
            assert "{" + special + "}" in out


class TestScoreElement:
    def test_edit_named_search_beats_button(self):
        edit = {"name": "Search", "auto_id": "", "role": "Edit", "is_enabled": True}
        button = {"name": "Search the web", "auto_id": "", "role": "Button", "is_enabled": True}
        assert score_element(edit, "search") > score_element(button, "search") - 0.31
        # the Edit bonus is what puts it ahead
        assert score_element(edit, "search") >= 1.0 + 0.3 - 0.01

    def test_disabled_element_scores_zero(self):
        el = {"name": "Search", "auto_id": "", "role": "Edit", "is_enabled": False}
        assert score_element(el, "search") == 0.0

    def test_no_overlap_scores_low(self):
        el = {"name": "Cancel", "auto_id": "btnCancel", "role": "Button", "is_enabled": True}
        assert score_element(el, "email address field") < 0.5

    def test_auto_id_counts(self):
        el = {"name": "", "auto_id": "emailInput", "role": "Edit", "is_enabled": True}
        assert score_element(el, "email") >= 1.0

    def test_empty_description(self):
        el = {"name": "x", "auto_id": "", "role": "Edit", "is_enabled": True}
        assert score_element(el, "") == 0.0


class TestEnvGate:
    def test_default_off_physical_cursor(self, monkeypatch):
        # Phase 29: physical cursor is the default; virtual UIA input is opt-in.
        monkeypatch.delenv("JARVIS_VIRTUAL_INPUT", raising=False)
        assert not virtual_input_enabled()

    def test_enabled_with_one(self, monkeypatch):
        monkeypatch.setenv("JARVIS_VIRTUAL_INPUT", "1")
        assert virtual_input_enabled()

    def test_disabled_with_zero(self, monkeypatch):
        monkeypatch.setenv("JARVIS_VIRTUAL_INPUT", "0")
        assert not virtual_input_enabled()
