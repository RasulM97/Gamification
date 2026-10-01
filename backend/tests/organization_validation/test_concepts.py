"""Conceptual counterexamples only: these tests do not certify production controls."""
from copy import deepcopy
import json
from pathlib import Path
from .concepts import resolve,team,members
DATA=json.loads(Path(__file__).with_name('dataset.json').read_text())
def scenario(key):return deepcopy(next(s for s in DATA['scenarios'] if s['id']==key))

def test_same_team_different_project_membership():
    s=scenario('project-task');s['actor']='4';assert resolve(s,True,'C')
    s['actor']='7';assert not resolve(s,True,'C')
    assert team('C',4,1000)==team('C',7,1000)=='Engineering'
    assert resolve(s,True,'B')  # Team membership cannot discriminate this pair.

def test_event_time_and_current_authority_are_distinct():
    s=scenario('historical-team-group');assert resolve(s,'UNRECOVERABLE','B')=='Engineering'
    assert team('D',4,4000)=='Sales'
    s=scenario('changed-manager');assert not resolve(s,True,'C')
    s['tick']=1000;assert resolve(s,True,'C')

def test_project_closure_does_not_erase_old_context():
    s=scenario('closed-project');assert not resolve(s,True,'C')
    s.update(operation='reporting',eventScope='Gamma');assert resolve(s,'UNRECOVERABLE','C')=='Gamma'
    assert 7 not in members('D','Alpha',4000) and 9 in members('D','Alpha',4000)

def test_concept_rejects_foreign_actor():
    s=scenario('team-task');s['actor']='A:1';assert not resolve(s,True,'B')
    s=scenario('project-task');s['actor']='A:1';assert not resolve(s,True,'C')

def test_resolvers_do_not_read_expected_answers():
    s=scenario('project-rule');before=resolve(s,True,'C');s['expected']='deliberately wrong oracle';assert resolve(s,True,'C')==before is False
