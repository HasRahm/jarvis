"""Tool-call/tool-response pairing must stay OpenAI-compatible (review finding #5).

The adapter must preserve model-provided tool_call ids, pair tool responses by id (with a FIFO
fallback for legacy callers), and never drop assistant tool_calls or invent orphan ids when the
history is well-formed. Getting this wrong causes intermittent 400s / context corruption.
"""
import os

os.environ.setdefault("JARVIS_CI", "true")

from core.system.llm_adapter import _format_messages_for_openai as fmt


def _asst(out):
    return next(m for m in out if m.get("tool_calls"))


def _tools(out):
    return [m for m in out if m["role"] == "tool"]


def test_explicit_ids_preserved_and_paired():
    out = fmt([
        {"role": "user", "content": "go"},
        {"role": "assistant", "tool_calls": [
            {"id": "call_AAA", "function": {"name": "open_app", "arguments": {"name": "x"}}},
            {"id": "call_BBB", "function": {"name": "read", "arguments": {}}},
        ]},
        {"role": "tool", "tool_call_id": "call_AAA", "content": "opened"},
        {"role": "tool", "tool_call_id": "call_BBB", "content": "text"},
    ])
    assert [c["id"] for c in _asst(out)["tool_calls"]] == ["call_AAA", "call_BBB"]
    assert [t["tool_call_id"] for t in _tools(out)] == ["call_AAA", "call_BBB"]


def test_legacy_tool_msgs_without_ids_fifo_match():
    # Tool responses with no tool_call_id (older dispatch loops) FIFO-match the assistant ids.
    out = fmt([
        {"role": "assistant", "tool_calls": [
            {"id": "call_X", "function": {"name": "a", "arguments": {}}},
            {"id": "call_Y", "function": {"name": "b", "arguments": {}}},
        ]},
        {"role": "tool", "content": "r1"},
        {"role": "tool", "content": "r2"},
    ])
    ids = [t["tool_call_id"] for t in _tools(out)]
    assert ids == ["call_X", "call_Y"]
    assert not any("orphan" in i for i in ids)


def test_missing_assistant_id_is_synthesized_and_paired():
    out = fmt([
        {"role": "assistant", "tool_calls": [{"function": {"name": "a", "arguments": {}}}]},
        {"role": "tool", "content": "r"},
    ])
    asst_id = _asst(out)["tool_calls"][0]["id"]
    tool_id = _tools(out)[0]["tool_call_id"]
    assert asst_id and asst_id == tool_id
    assert "orphan" not in tool_id


def test_all_tool_calls_kept_not_dropped_by_count():
    # The old global-count heuristic could silently drop calls; all must survive now.
    out = fmt([
        {"role": "assistant", "tool_calls": [
            {"id": "c1", "function": {"name": "a", "arguments": {}}},
            {"id": "c2", "function": {"name": "b", "arguments": {}}},
            {"id": "c3", "function": {"name": "c", "arguments": {}}},
        ]},
        {"role": "tool", "tool_call_id": "c1", "content": "r1"},
        {"role": "tool", "tool_call_id": "c2", "content": "r2"},
        {"role": "tool", "tool_call_id": "c3", "content": "r3"},
    ])
    assert len(_asst(out)["tool_calls"]) == 3


def test_assistant_arguments_serialized_to_string():
    out = fmt([
        {"role": "assistant", "tool_calls": [
            {"id": "c1", "function": {"name": "a", "arguments": {"k": "v"}}},
        ]},
        {"role": "tool", "tool_call_id": "c1", "content": "r"},
    ])
    args = _asst(out)["tool_calls"][0]["function"]["arguments"]
    assert isinstance(args, str) and '"k"' in args


def test_plain_assistant_content_never_empty():
    out = fmt([{"role": "assistant", "content": ""}])
    assert out[0]["content"].strip()
