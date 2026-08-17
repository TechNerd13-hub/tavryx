from tavryx.memory import MemoryStore
from tavryx.models import Situation, Mode


def test_candidates_keep_multiple_living_threads(tmp_path):
    m = MemoryStore(tmp_path / 't.db')
    a = Situation(situation_id='S-AAA11111', title='Payment outage', mode=Mode.INCIDENT)
    b = Situation(situation_id='S-BBB22222', title='Recursion study', mode=Mode.LEARNING)
    m.add('ayusman', 'discord', 'payments failing', a)
    m.add('ayusman', 'discord', 'teach recursion', b)
    ids = {x['situation_id'] for x in m.candidates('ayusman', 8)}
    assert ids == {'S-AAA11111', 'S-BBB22222'}


def test_timeline_is_ordered_oldest_to_newest(tmp_path):
    m = MemoryStore(tmp_path / 't.db')
    s = Situation(situation_id='S-CCC33333', title='Deployment', mode=Mode.DECISION)
    m.add('u', 'email', 'first', s)
    s.summary = 'second state'
    m.add('u', 'discord', 'second', s)
    rows = list(reversed(m.history_for('S-CCC33333', 8)))
    assert rows[0]['input_text'] == 'first'
    assert rows[-1]['input_text'] == 'second'
