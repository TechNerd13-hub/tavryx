from tavryx.models import Mode, Situation

def test_situation_defaults():
    s = Situation()
    assert s.mode == Mode.GENERAL
    assert 0 <= s.confidence <= 100

def test_adaptive_fields():
    s = Situation(title="Incident", mode="INCIDENT", severity="CRITICAL", decision_revised=True)
    assert s.mode == Mode.INCIDENT
    assert s.decision_revised


def test_reasoning_level_default():
    s = Situation()
    assert s.reasoning_level == "FAST"
