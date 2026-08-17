from tavryx.memory import MemoryStore
from tavryx.models import Situation, Lifecycle
from tavryx.engine import command_response

def test_situation_gets_id(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    s = store.add("a", "discord", "hello", Situation(title="A"))
    assert s.situation_id.startswith("S-")

def test_park_and_resume(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    s = store.add("a", "discord", "hello", Situation(title="Project"))
    assert store.park(s.situation_id).lifecycle == Lifecycle.PARKED
    assert store.resume(s.situation_id).lifecycle == Lifecycle.ACTIVE

def test_situations_command(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    s = store.add("a", "discord", "hello", Situation(title="Project"))
    out = command_response("/situations", store)
    assert s.situation_id in out and "Project" in out

def test_park_command(tmp_path):
    store = MemoryStore(tmp_path / "t.db")
    s = store.add("a", "discord", "hello", Situation(title="Project"))
    out = command_response("/park", store, s.situation_id)
    assert "PARKED" in out
