"""Real Cortex HTTP -> production Runtime adapter -> Sophie prompt contract.

Semantic model quality is not faked into an end-to-end claim: fixtures represent
validated stored evidence. No model, remote database or provider calls here.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlmodel import select

RUNTIME = Path(os.environ.get('CONTINUITY_RUNTIME_PATH', str(Path(__file__).resolve().parents[2] / 'companion-runtime-continuity-basics-v0')))
sys.path.insert(0, str(RUNTIME))
# Both checked-out applications supply their existing local test dependencies.
for site_packages in (RUNTIME / ".venv/lib").glob("python*/site-packages"):
    sys.path.append(str(site_packages))
from adapters.cortex.client import CortexAdapter
from companion_core.prompts.sophie_prompt_builder import build_sophie_reply_system_prompt
from src.db import async_session_maker
from src.models.attention_candidate import AttentionCandidate, AttentionCandidateKind, AttentionCandidateStatus
from src.models.clarification import ClarificationCandidate, ClarificationType
from src.models.derived_signal import DerivedSignal
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.models.suppression import Suppression, SuppressionTarget

NOW = datetime(2026, 9, 24, 9, tzinfo=timezone.utc)
WS, OWNER, SESSION = 'basics-v0', 'user_alice', 'chat_one'

@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setenv('HONCHO_WORKSPACE_ID', WS)
    monkeypatch.setenv('SYNAPSE_CORTEX_URL', 'http://test')
    monkeypatch.setenv('SYNAPSE_CORTEX_ENABLED', 'true')
    monkeypatch.setenv('SYNAPSE_CORTEX_CONTEXT_ENABLED', 'true')
    monkeypatch.setenv('SYNAPSE_CORTEX_TIMEOUT_MS', '10000')
    from src.routers import v1_cortex
    monkeypatch.setattr(v1_cortex, 'get_agenda_adapter', lambda: None)

async def store(*rows):
    async with async_session_maker() as db:
        db.add_all(rows)
        await db.commit()

async def foreground(client, text='Hello again', chat='one'):
    adapter = CortexAdapter(base_url='http://test', http_client=client)
    context = await adapter.fetch_cortex_context(
        user_id='alice', chat_id=chat, now=NOW, turn_text=text,
        last_interaction_time=NOW-timedelta(days=2),
        entry_context={'chronology': {'temporalSession': 'new', 'gapMinutes': 2880}},
    )
    assert context is not None
    prompt = build_sophie_reply_system_prompt(
        now=NOW, time_zone='Europe/London', interaction_mode='social',
        cortex_context=context, base_prompt='You are Sophie.',
        director_plan={'intent':'social','primaryAct':'react','objective':'Respond to incoming turn'},
    )
    return context, prompt

def attention(topic, **kw):
    return AttentionCandidate(honcho_workspace_id=WS, honcho_session_id=SESSION,
        owner_peer_id=OWNER, source_message_id='evidence:'+topic, candidate_key=topic,
        kind=AttentionCandidateKind.REENTRY, content=topic, salience=.9, confidence=.95,
        not_before=NOW.replace(tzinfo=None)-timedelta(hours=1),
        created_at=NOW.replace(tzinfo=None)-timedelta(days=2), **kw)

@pytest.mark.asyncio
async def test_natural_checkin_reaches_actual_sophie_foreground(async_client):
    await store(attention('Friend in hospital; user worried; outcome unknown'))
    _, prompt = await foreground(async_client)
    assert 'Friend in hospital' in prompt
    assert 'not an obligation' in prompt.lower() or 'optional' in prompt.lower()

@pytest.mark.asyncio
async def test_unresolved_intention_reaches_foreground_without_task(async_client):
    await store(OpenLoop(honcho_workspace_id=WS, honcho_session_id=SESSION,
        owner_peer_id=OWNER, honcho_message_id='application-evidence',
        title='Cambridge application', summary='User intends to apply; not an accepted task',
        created_at=NOW.replace(tzinfo=None)-timedelta(days=1)))
    _, prompt = await foreground(async_client)
    assert 'Cambridge application' in prompt

@pytest.mark.asyncio
async def test_clarification_reaches_foreground_without_inventing_target(async_client):
    await store(ClarificationCandidate(honcho_workspace_id=WS, honcho_session_id=SESSION,
        honcho_message_id='ambiguous-message', clarification_type=ClarificationType.UNCLEAR_TARGET,
        description='Which item did you move to Friday?', created_at=NOW.replace(tzinfo=None)))
    _, prompt = await foreground(async_client, 'I moved it to Friday.')
    assert 'Which item did you move to Friday?' in prompt

@pytest.mark.asyncio
async def test_suppression_applies_to_attention_including_reentry(async_client):
    await store(attention('Friend in hospital; outcome unknown'),
        Suppression(honcho_workspace_id=WS, honcho_session_id=SESSION,
            honcho_message_id='suppress', owner_peer_id=OWNER, target_type=SuppressionTarget.TOPIC,
            topic_or_entity='Friend in hospital', reason='user_explicit_suppression',
            reopen_condition='user_mentions_topic'))
    context, _ = await foreground(async_client, chat='two')
    ho=context.continuityContext['handover']
    assert not any('hospital' in json.dumps(x).lower() for x in ho.get('available',[]))
    packet=await async_client.get('/v1/cortex/attention-packet',params={
        'workspace_id':WS,'session_id':'chat_two','peer_id':OWNER,'now':NOW.isoformat()})
    assert packet.status_code==200
    assert packet.json()['sophie_attention']==[]

@pytest.mark.asyncio
async def test_compilation_does_not_count_as_asking(async_client):
    await store(ClarificationCandidate(honcho_workspace_id=WS,honcho_session_id=SESSION,
        honcho_message_id='ambiguity', clarification_type=ClarificationType.UNCLEAR_TARGET,
        description='Which appointment?',created_at=NOW.replace(tzinfo=None)))
    for _ in range(2):
        await foreground(async_client)
    async with async_session_maker() as db:
        rows=(await db.execute(select(DerivedSignal))).scalars().all()
        assert not any('clarification:' in row.payload_json for row in rows)

@pytest.mark.asyncio
async def test_reentry_is_bounded_and_omits_resolved_dismissed_backlog(async_client):
    await store(attention('Friend in hospital; important unresolved matter'),
        attention('Resolved application',status=AttentionCandidateStatus.RESOLVED),
        attention('Dismissed holiday',status=AttentionCandidateStatus.DISMISSED))
    context,prompt=await foreground(async_client)
    assert 'Friend in hospital' in prompt
    assert 'Resolved application' not in prompt and 'Dismissed holiday' not in prompt
    assert len(context.continuityContext['handover'].get('available',[]))<=1
    assert context.orientation=='returning'

@pytest.mark.asyncio
async def test_ordinary_turn_latency_sample(async_client):
    samples=[]
    for _ in range(12):
        start=time.perf_counter()
        await foreground(async_client,'Hello')
        samples.append(round((time.perf_counter()-start)*1000,3))
    report={'boundary':'real Cortex ASGI HTTP + production Runtime adapter + Sophie prompt; no LLM/network','samples_ms':samples,'median_ms':sorted(samples)[len(samples)//2]}
    target=os.environ.get('CONTINUITY_LATENCY_OUTPUT')
    if target: Path(target).write_text(json.dumps(report,indent=2))
    print(json.dumps(report))

async def effect(client, candidate, stage, effect=None, owner=OWNER, decision='decision', rid=None):
    return await client.post('/v1/cortex/candidate-receipts',json={
        'contract_version':'candidate-receipts-v1','workspace_id':WS,'owner_peer_id':owner,
        'receipts':[{'receipt_id':rid or decision+stage,'decision_id':decision,'turn_id':'turn',
            'candidate_id':candidate['candidate_id'],'candidate_version':candidate['candidate_version'],
            'stage':stage,'channel':'inbound','assistant_message_id':'assistant-1',
            'occurred_at':NOW.isoformat(),'effect':effect}]})

@pytest.mark.asyncio
async def test_real_receipts_separate_inclusion_persistence_asking_and_resolution(async_client):
    from src.models.operational_state import CandidateReceipt
    row=attention('Hospital outcome unknown')
    await store(row)
    context,_=await foreground(async_client)
    offered=context.continuityContext['handover']['available'][0]
    for stage in ('selected','included_in_context','persisted'):
        assert (await effect(async_client,offered,stage)).status_code==200
    assert len((await foreground(async_client))[0].continuityContext['handover']['available'])==1
    assert (await effect(async_client,offered,'generated','asked')).status_code==200
    assert (await effect(async_client,offered,'generated','asked')).json()['duplicates']==1
    assert (await foreground(async_client))[0].continuityContext['handover']['available']==[]
    async with async_session_maker() as db:
        saved=await db.get(AttentionCandidate,row.id)
        assert saved.status==AttentionCandidateStatus.ACTIVE  # still unresolved
        assert saved.surfaced_count==1
        receipts=(await db.execute(select(CandidateReceipt))).scalars().all()
        assert {r.stage for r in receipts}=={'selected','included_in_context','persisted','generated'}
    assert (await effect(async_client,offered,'generated','asked',owner='another-user',decision='foreign')).status_code==404
    stale={**offered,'candidate_version':'old'}
    assert (await effect(async_client,stale,'generated','asked',decision='stale')).status_code==409

@pytest.mark.asyncio
@pytest.mark.parametrize('kind,action', [('attention','fulfill'),('open_loop','cancel'),('clarification','fulfill')])
async def test_user_outcome_uses_existing_lifecycle_and_preserves_evidence(async_client,monkeypatch,kind,action):
    from src.routers import v1_events
    from src.schemas.candidate import ExtractionCandidate
    from src.models.clarification import ClarificationStatus
    if kind=='attention': row=attention('Hospital outcome unknown')
    elif kind=='open_loop': row=OpenLoop(honcho_workspace_id=WS,honcho_session_id=SESSION,
        owner_peer_id=OWNER,honcho_message_id='original',title='Cambridge application',summary='Considering applying')
    else: row=ClarificationCandidate(honcho_workspace_id=WS,honcho_session_id=SESSION,
        owner_peer_id=OWNER,honcho_message_id='original',description='Which appointment?')
    await store(row)
    text='My friend is home now.' if kind=='attention' else ('I abandoned the Cambridge application.' if kind=='open_loop' else 'I meant the dentist appointment.')
    candidate=ExtractionCandidate(candidate_key='outcome',observation=text,raw_evidence=text,
        actor_peer_id=OWNER,operational_kind='completion' if action=='fulfill' else 'cancellation',
        resolution_hint={'target_kind':kind,'target_id':str(row.id),'action':action,'evidence':text})
    monkeypatch.setattr(v1_events.turn_extractor,'extract_candidates',lambda *a,**kw:[candidate])
    payload={'workspace_id':WS,'session_id':SESSION,'honcho_message_id':'user-outcome',
        'peer_id':OWNER,'text':text,'now':NOW.isoformat(),'timezone':'Europe/London'}
    first=await async_client.post('/v1/events/turn',json=payload)
    assert first.status_code==202,first.text
    assert (await async_client.post('/v1/events/turn',json=payload)).status_code==202
    async with async_session_maker() as db:
        saved=await db.get(type(row),row.id)
        assert saved.status in (AttentionCandidateStatus.RESOLVED,OpenLoopStatus.ABANDONED,ClarificationStatus.RESOLVED)
        assert (saved.source_message_id if kind=='attention' else saved.honcho_message_id) != 'user-outcome'
    context,_=await foreground(async_client)
    assert context.continuityContext['handover']['available']==[]
    assert context.continuityContext['handover']['clarifications']==[]

@pytest.mark.asyncio
async def test_hypothetical_outcome_does_not_resolve_attention():
    from src.schemas.candidate import ExtractionCandidate
    from src.services.lifecycle_service import LifecycleService
    row=attention('Friend in hospital')
    await store(row)
    candidate=ExtractionCandidate(candidate_key='hypothetical',observation='If he came home',is_hypothetical=True,
        resolution_hint={'target_kind':'attention','target_id':str(row.id),'action':'fulfill'})
    async with async_session_maker() as db:
        changed=await LifecycleService().handle_outcome_mutations(db,WS,SESSION,'hypothetical',candidate,NOW,OWNER)
        assert changed==[]
        assert (await db.get(AttentionCandidate,row.id)).status==AttentionCandidateStatus.ACTIVE

@pytest.mark.asyncio
async def test_task_mode_keeps_incoming_request_ahead_of_optional_matters(async_client):
    await store(attention('Friend in hospital'))
    context,_=await foreground(async_client)
    prompt=build_sophie_reply_system_prompt(now=NOW,time_zone='Europe/London',
        cortex_context=context,base_prompt='You are Sophie.',
        director_plan={'intent':'task','primaryAct':'answer','objective':'Answer the incoming calculation'})
    assert 'Friend in hospital' not in prompt

@pytest.mark.asyncio
async def test_cached_rank_cannot_revive_suppressed_item():
    from src.services.agenda_service import compile_agenda
    p={'intelligence_brief':{'backstage_attention':[{'id':'one','content':'Friend in hospital'}]}}
    async with async_session_maker() as db:
        first=await compile_agenda(db,workspace_id=WS,owner_peer_id=OWNER,packet=p,
            now=NOW,timezone_str='UTC',adapter=None,schedule_background=False)
        assert len(first['items'])==1
        second=await compile_agenda(db,workspace_id=WS,owner_peer_id=OWNER,packet={},
            now=NOW,timezone_str='UTC',adapter=None,schedule_background=False)
        assert second['items']==[]

@pytest.mark.asyncio
async def test_source_owned_reminders_have_no_second_cortex_executor():
    from src.models.expectation import Expectation,ExpectationType
    from src.services.reminder_executor import due_reminders
    row=Expectation(honcho_workspace_id=WS,honcho_session_id=SESSION,honcho_message_id='task-source',
        owner_peer_id=OWNER,subject_peer_id=OWNER,expectation_type=ExpectationType.USER_COMMITMENT,title='Call Mum',summary='Explicit task',
        source_system='app_task',source_object_id='task-one',
        reminder_windows_json=json.dumps([{'start':NOW.isoformat()}]))
    await store(row)
    async with async_session_maker() as db:
        assert await due_reminders(db,workspace_id=WS,owner_peer_id=OWNER,now=NOW)==[]
        saved=await db.get(Expectation,row.id)
        assert 'fired' not in json.loads(saved.reminder_windows_json)[0]

@pytest.mark.asyncio
async def test_future_attention_waits_and_other_owner_never_sees_it(async_client):
    row=attention('Friend in hospital')
    row.not_before=NOW.replace(tzinfo=None)+timedelta(hours=2)
    await store(row)
    assert (await foreground(async_client))[0].continuityContext['handover']['available']==[]
    later=await async_client.get('/v1/cortex/attention-packet',params={'workspace_id':WS,
        'session_id':SESSION,'peer_id':OWNER,'now':(NOW+timedelta(hours=3)).isoformat()})
    assert len(later.json()['sophie_attention'])==1
    other=await async_client.get('/v1/cortex/attention-packet',params={'workspace_id':WS,
        'session_id':SESSION,'peer_id':'other-owner','now':(NOW+timedelta(hours=3)).isoformat()})
    assert other.json()['sophie_attention']==[]

@pytest.mark.asyncio
async def test_promoted_linked_loop_does_not_compete_with_canonical_task(async_client):
    from src.models.expectation import Expectation,ExpectationType,OutcomeState
    exp=Expectation(honcho_workspace_id=WS,honcho_session_id=SESSION,honcho_message_id='intention',
        owner_peer_id=OWNER,subject_peer_id=OWNER,expectation_type=ExpectationType.USER_COMMITMENT,
        title='Cambridge application',summary='Intends to apply')
    await store(exp)
    loop=OpenLoop(honcho_workspace_id=WS,honcho_session_id=SESSION,owner_peer_id=OWNER,
        honcho_message_id='intention',expectation_id=exp.id,title='Cambridge application',summary='Unresolved')
    await store(loop)
    r=await async_client.post('/v1/events/object',json={'workspace_id':WS,'session_id':SESSION,
        'peer_id':OWNER,'owner_peer_id':OWNER,'now':NOW.isoformat(),'timezone':'Europe/London',
        'source':{'system':'app_task','object_id':'cambridge-task','version':1,'kind':'task'},
        'action':'created','title':'Cambridge application','reminder_windows':[],
        'absorbs':[{'kind':'open_loop','id':str(loop.id)}]})
    assert r.status_code==202,r.text
    context,_=await foreground(async_client)
    assert context.continuityContext['handover']['available']==[]
    async with async_session_maker() as db:
        previous=await db.get(Expectation,exp.id)
        assert previous.outcome_state==OutcomeState.SUPERSEDED
        assert (await db.get(OpenLoop,loop.id)).expectation_id==previous.superseded_by_id

@pytest.mark.asyncio
async def test_repeated_proactive_ticks_cannot_offer_suppressed_attention(async_client):
    await store(attention('Friend in hospital'),Suppression(honcho_workspace_id=WS,
        honcho_session_id=SESSION,honcho_message_id='no-thanks',owner_peer_id=OWNER,
        target_type=SuppressionTarget.TOPIC,topic_or_entity='Friend in hospital',reason='explicit'))
    for _ in range(2):
        r=await async_client.post('/v1/cortex/initiative/tick',json={'workspace_id':WS,
            'session_id':SESSION,'peer_id':OWNER,'now':NOW.isoformat(),'timezone':'Europe/London'})
        assert r.status_code==200,r.text
        assert r.json()['should_appear'] is False
        assert r.json()['item'] is None

@pytest.mark.asyncio
async def test_ingested_uncertainty_is_consumed_by_foreground_without_mutation(async_client,monkeypatch):
    from src.routers import v1_events
    from src.schemas.candidate import ExtractionCandidate
    from src.models.expectation import Expectation
    cand=ExtractionCandidate(candidate_key='ambiguous',observation='I moved it to Friday.',
        raw_evidence='I moved it to Friday.',clarification_hint={'question':'Which item did you move to Friday?'})
    monkeypatch.setattr(v1_events.turn_extractor,'extract_candidates',lambda *a,**kw:[cand])
    r=await async_client.post('/v1/events/turn',json={'workspace_id':WS,'session_id':SESSION,
        'honcho_message_id':'ambiguous-turn','peer_id':OWNER,'text':cand.raw_evidence,
        'now':NOW.isoformat(),'timezone':'Europe/London'})
    assert r.status_code==202,r.text
    _,prompt=await foreground(async_client,'I moved it to Friday.',chat='two')
    assert 'Which item did you move to Friday?' in prompt
    async with async_session_maker() as db:
        assert (await db.execute(select(Expectation))).scalars().all()==[]
        row=(await db.execute(select(ClarificationCandidate))).scalar_one()
        assert row.owner_peer_id==OWNER
