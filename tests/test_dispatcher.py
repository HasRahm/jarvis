"""Tests for the tool dispatcher.

Verifies: tool schema structure, CORTEX_EXEMPT membership, required fields,
and that dispatch() returns an error string (not raises) for unknown tools.
"""
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def tool_defs():
    from tools.dispatcher import TOOL_DEFINITIONS
    return TOOL_DEFINITIONS


@pytest.fixture(scope="module")
def tool_names(tool_defs):
    return {t["function"]["name"] for t in tool_defs}


@pytest.fixture(scope="module")
def cortex_exempt_source():
    """Read the CORTEX_EXEMPT set from the dispatcher source (it's local to dispatch())."""
    import inspect
    import tools.dispatcher as _d
    return inspect.getsource(_d.dispatch)


# ── Schema structure ──────────────────────────────────────────────────────────

class TestToolSchema:
    def test_minimum_tool_count(self, tool_defs):
        """We expect at least 20 registered tools."""
        assert len(tool_defs) >= 20, f"Only {len(tool_defs)} tools registered"

    def test_each_tool_has_type_function(self, tool_defs):
        for t in tool_defs:
            assert t.get("type") == "function", f"{t} missing type=function"

    def test_each_function_has_name(self, tool_defs):
        for t in tool_defs:
            assert "name" in t["function"], f"Tool missing name: {t}"

    def test_each_function_has_description(self, tool_defs):
        for t in tool_defs:
            fn = t["function"]
            assert fn.get("description"), f"Tool {fn.get('name')} has no description"

    def test_each_function_has_parameters_object(self, tool_defs):
        for t in tool_defs:
            fn     = t["function"]
            params = fn.get("parameters", {})
            assert params.get("type") == "object", \
                f"Tool {fn['name']} parameters.type should be 'object'"

    def test_no_duplicate_tool_names(self, tool_defs):
        names = [t["function"]["name"] for t in tool_defs]
        assert len(names) == len(set(names)), "Duplicate tool names found"

    def test_required_fields_exist_in_properties(self, tool_defs):
        """Every required field must appear in properties."""
        for t in tool_defs:
            fn       = t["function"]
            params   = fn.get("parameters", {})
            required = params.get("required", [])
            props    = params.get("properties", {})
            for field in required:
                assert field in props, \
                    f"Tool {fn['name']}: required field '{field}' not in properties"


class TestCoreToolsPresent:
    """Essential tools must always be registered."""

    REQUIRED = [
        "read_file", "write_file", "list_dir",
        "run_command",
        "browser_navigate", "browser_extract_text",
        "brain_query", "brain_write",
        "desktop_smooth_click", "desktop_type_text",
        "screen_ocr",
    ]

    def test_core_tools_registered(self, tool_names):
        for name in self.REQUIRED:
            assert name in tool_names, f"Required tool '{name}' not registered"

    def test_visual_tools_registered(self, tool_names):
        for name in ("visual_inspect", "visual_click"):
            assert name in tool_names, f"Visual tool '{name}' not registered"

    def test_vocab_learn_registered(self, tool_names):
        assert "vocab_learn" in tool_names


class TestCortexExempt:
    """Safety-critical and perception tools must be listed in the CORTEX_EXEMPT block."""

    MUST_BE_EXEMPT = [
        "visual_inspect",
        "visual_click",
        "vocab_learn",
        "brain_query",
        "brain_write",
        "screen_ocr",
    ]

    def test_perception_tools_are_exempt(self, cortex_exempt_source):
        for name in self.MUST_BE_EXEMPT:
            assert f'"{name}"' in cortex_exempt_source or f"'{name}'" in cortex_exempt_source, \
                f"Tool '{name}' should appear in _CORTEX_EXEMPT inside dispatch()"

    def test_cortex_exempt_block_exists(self, cortex_exempt_source):
        assert "_CORTEX_EXEMPT" in cortex_exempt_source


class TestDispatch:
    """dispatch() raises ValueError for unknown tools — verify it never silently succeeds."""

    def test_unknown_tool_raises_value_error(self):
        from tools.dispatcher import dispatch
        with pytest.raises((ValueError, Exception)) as exc_info:
            dispatch("no_such_tool_xyz", "{}")
        assert "no_such_tool_xyz" in str(exc_info.value) or "Unknown" in str(exc_info.value)

    def test_dispatch_json_string_raises_not_silently_succeeds(self):
        """Passing a JSON string for an unknown tool should raise, not silently return None."""
        from tools.dispatcher import dispatch
        with pytest.raises((ValueError, Exception)):
            dispatch("no_such_tool_xyz", json.dumps({"key": "value"}))
