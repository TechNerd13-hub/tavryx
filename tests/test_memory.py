from tavryx.memory import MemoryStore
from tavryx.models import Situation

def test_memory_roundtrip(tmp_path):
    store = MemoryStore(tmp_path / "test.db")
    store.add("tester", "test", "hello", Situation(title="Test"))
    assert store.latest().title == "Test"
    assert len(store.recent(10)) == 1
