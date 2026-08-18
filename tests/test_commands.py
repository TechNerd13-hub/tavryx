from tavryx.memory import MemoryStore
from tavryx.models import Situation
from tavryx.engine import command_response

def test_focus(tmp_path):
    store = MemoryStore(tmp_path / "test.db")
    store.add("tester", "test", "incident", Situation(next_move="Check logs", why="Highest leverage", confidence=95))
    out = command_response("/focus", store)
    assert "Check logs" in out and "95%" in out

def test_reset(tmp_path):
    store = MemoryStore(tmp_path / "test.db")
    store.add("tester", "test", "x", Situation(title="X"))
    assert "RESET" in command_response("/reset", store)
    assert store.latest() is None


def test_all_dashboard_commands(tmp_path):
    store = MemoryStore(tmp_path / "test.db")
    store.add(
        "tester", "test", "incident",
        Situation(
            situation_id="S-DEMO",
            title="Payment incident",
            summary="Checkout failures persist.",
            state_delta="Errors fell after rollback.",
            next_move="Check the payment region.",
            why="Failures correlate with the deployment.",
            confidence=92,
            severity="HIGH",
            trajectory="DETERIORATING",
        ),
    )
    for command in ["/focus", "/brief", "/why", "/state", "/timeline"]:
        out = command_response(command, store)
        assert out and "TAVRYX" in out
