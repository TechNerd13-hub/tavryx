from tavryx.engine import TavryxEngine
from tavryx.memory import MemoryStore
from tavryx.models import Situation

def test_thinking_policy_is_fast_for_simple_messages(tmp_path):
    e = object.__new__(TavryxEngine)
    e.memory = MemoryStore(tmp_path / "t.db")
    assert e._thinking_level("hello, what is recursion?", None) == "minimal"

def test_thinking_policy_escalates_for_critical_messages(tmp_path):
    e = object.__new__(TavryxEngine)
    e.memory = MemoryStore(tmp_path / "t.db")
    assert e._thinking_level("production API is returning HTTP 500 errors for customers", None) == "medium"

def test_thinking_policy_escalates_for_complex_decisions(tmp_path):
    e = object.__new__(TavryxEngine)
    e.memory = MemoryStore(tmp_path / "t.db")
    assert e._thinking_level("compare architecture options and help me choose a deployment strategy", None) == "low"
