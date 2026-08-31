"""TRACK B - Stage 1 foreground-model qualification shootout.

Frozen real production input packets (kernel + live agenda + scene + direction
+ recent turns). The FOREGROUND MODEL is the only variable. Mechanism/extraction
is identical for every model by construction. Outputs per-model responses,
latency, cost, and a judge-scored weighted aggregate across capability dims.
Models under test: deepseek v4 flash (baseline), gpt-5.6-luna-pro, and the
founder-provided candidates. Personality is NOT the criterion; judgement is.
"""
import json, time, urllib.request, os

ORKEY=[l.split('=',1)[1].strip() for l in open(os.path.join(os.path.dirname(__file__),'..','.env')) if l.startswith('OPENROUTER_API_KEY')][0]
KERNEL=open('/Users/mukeshkumar/play/companion-runtime/companion_core/profiles/sophie.py').read().split('SOPHIE_BASE_SYSTEM_PROMPT = """')[1].split('""".strip()')[0] if os.path.exists('/Users/mukeshkumar/play/companion-runtime/companion_core/profiles/sophie.py') else ''
if not KERNEL:
    KERNEL=open('companion_core/profiles/sophie.py').read().split('SOPHIE_BASE_SYSTEM_PROMPT = """')[1].split('""".strip()')[0]

MODELS=[
 "deepseek/deepseek-v4-flash",            # production baseline
 "openai/gpt-5.6-luna-pro",               # Luna Pro (exact prod gear slug)
 "minimax/minimax-m3",
 "upstage/solar-pro4",
 "meta/muse-spark-1.2-contributor",
 "z-ai/glm-5.3-flash",
 "nvidia/nemotron-3.5-lightning",
]

AGENDA_WALK='''[{"what":"daily step goal (10000 steps)","owner":"user","status":"unresolved","pressure":"high","next_move":"ask status; adapt strategy if window closed"},{"what":"Prepare tomorrow's meeting with Anna (promotion conversation)","owner":"user","status":"unresolved","pressure":"medium","next_move":"offer prep help if natural"}]'''
AGENDA_LIGHT='[{"what":"Rome birthday trip - dates unset","owner":"shared","status":"unresolved","pressure":"low","next_move":"raise at a natural opening"}]'
AGENDA_EMOTION='[{"what":"User felt left out while family gathered yesterday","owner":"user","status":"acknowledged","pressure":"low","next_move":"do not re-litigate; support if he returns to it"}]'

S=[
 dict(name="bounce_tiny_social", agenda=AGENDA_LIGHT, scene="Friday 21:40, casual",
      history=[], turn="look at this \U0001F602",
      focus="resist assistant sludge; a reaction may be the whole reply"),
 dict(name="unrelated_reentry_agenda_steering", agenda=AGENDA_WALK, scene="Wednesday 11:30, morning walk unresolved, window closing",
      history=[("user","morning"),("assistant","Morning. Big day?")],
      turn="hey random thing - what do you think about the new doctor who cast?",
      focus="answer naturally AND find an opening to bring the unresolved walk in"),
 dict(name="agenda_deferral_important", agenda=AGENDA_WALK, scene="Wednesday 11:32",
      history=[("user","hey random thing - thoughts on the new doctor who cast?"),("assistant","Cast looks risky but interesting. Why, you watching it?")],
      turn="also, I just found out my sister is in hospital. I need to process this.",
      focus="defer the walk agenda instantly; the sister thing dominates"),
 dict(name="mild_emotion_scope", agenda=AGENDA_EMOTION, scene="Sunday 19:00",
      history=[], turn="I'm a little sad I missed everyone today.",
      focus="acknowledge the specific event; do NOT expand into broad psychological narrative"),
 dict(name="user_correction", agenda=AGENDA_EMOTION, scene="Sunday 19:05",
      history=[("user","I'm sad I missed everyone"),("assistant","Is it the family part that gets to you most, or missing Oxford?")],
      turn="No, that's not what I meant. I'm annoyed about the transport, not sad about people.",
      focus="update immediately; never defend the prior inference"),
 dict(name="substantive_discussion", agenda=AGENDA_LIGHT, scene="Saturday 13:00, relaxed",
      history=[], turn="I think the rise of the far right in Europe is being deliberately funded by American billionaires and amplified on social media. My mate thinks it's just organic anger. What do you think?",
      focus="depth + nuance + an actual opinion; keep the conversation alive rather than closing with an essay"),
 dict(name="strong_followup", agenda=AGENDA_LIGHT, scene="Saturday 13:20, mid-discussion",
      history=[("user","I think the far right rise is funded by American billionaires."),("assistant","The funding is documented, but I'd argue they're buying permission and deregulation more than destabilisation - destabilisation is the side effect. Which part convinced you?")],
      turn="honestly the way everyone just accepts it now. like the outrage is the product.",
      focus="choose ONE genuinely interesting specific follow-up, not generic filler"),
 dict(name="messy_multi_intent", agenda=AGENDA_WALK, scene="Tuesday 12:10, overcast, windy",
      history=[], turn="shit I was meant to sort that thing for tomorrow but I got distracted and I'm going out now, remind me later yeah. need milk btw and loo roll, oh and don't let me forget that form before Friday",
      focus="separate plan / uncertainty / reminder / deadline without becoming a task bot"),
 dict(name="plan_failure_objective_persists", agenda=AGENDA_WALK, scene="Tuesday 19:30, daylight nearly gone, walk unconfirmed",
      history=[("user","going to try to get out for a walk this afternoon"),("assistant","Good. Bank it before it gets dark.")],
      turn="didn't manage it, got slammed with work",
      focus="objective still alive: offer adaptation, no nagging, no moralising, no 'you missed the window'"),
 dict(name="scene_time_awareness", agenda=AGENDA_WALK, scene="Tuesday 22:15, user heading to bed",
      history=[("user","yeah I did 11.2k steps earlier"),("assistant","Overachiever. Objective smashed.")],
      turn="ok I'm done for today, heading to bed",
      focus="use time + already-resolved state; no stale agenda pressure; warm sign-off"),
 dict(name="banter_serious_banter", agenda=AGENDA_LIGHT, scene="Saturday 21:00, drinks with friends",
      history=[("user","we're doing shots lol"),("assistant","Oh no. Say your goodbyes now.")],
      turn="ok serious question - do you think I actually have a shot at that promotion?",
      focus="register shift: drop the banter, be genuine and specific, then can return light"),
 dict(name="nothing_worth_steering", agenda=AGENDA_LIGHT, scene="Sunday 15:00, lazy afternoon",
      history=[("user","this show is amazing"),("assistant","Told you. What episode?")],
      turn="episode 6. it just keeps getting better",
      focus="agenda is low-salience: just have a normal conversation, leave the agenda alone"),
]

def chat(model,messages,max_tokens=300,temperature=0.8):
    body={'model':model,'messages':messages,'max_tokens':max_tokens,'temperature':temperature}
    req=urllib.request.Request('https://openrouter.ai/api/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':f'Bearer {ORKEY}'})
    t0=time.time()
    with urllib.request.urlopen(req,timeout=90) as r: res=json.loads(r.read())
    dt=round((time.time()-t0)*1000)
    u=res.get('usage') or {}
    return (res['choices'][0]['message']['content'] or '(empty)'), dt, u.get('total_tokens'), u

def context(sc, model_specific_direction=True):
    parts=[KERNEL, f"\n[LIVE AGENDA] {sc['agenda']}", f"\n[SCENE] {sc['scene']}"]
    if sc.get('history'):
        h='\n'.join(f"{'Him' if r=='user' else 'You'}: {c}" for r,c in sc['history'])
        parts.append(f"\n[RECENT CONVERSATION]\n{h}")
    if model_specific_direction:
        parts.append(f"\n[DIRECTION] Trajectory guidance: {sc['focus']} — direction, not a script. His latest statement outranks all context.")
    parts.append(f"\nHim: {sc['turn']}\nYou:")
    return '\n'.join(parts)

results={}
for model in MODELS:
    results[model]={'scenarios':[],'total_ms':0,'total_tokens':0,'n':0}
    for sc in S:
        try:
            reply,ms,tk,u=chat(model,[{'role':'system','content':context(sc)}],max_tokens=300)
        except Exception as e:
            reply,ms,tk=f"ERROR {type(e).__name__}: {e}",0,0
        results[model]['scenarios'].append({'name':sc['name'],'reply':reply,'ms':ms,'tokens':tk,'focus':sc['focus']})
        results[model]['total_ms']+=ms; results[model]['total_tokens']+=tk or 0; results[model]['n']+=1
        print(f"  {model.split('/')[-1][:24]:24s} {sc['name'][:34]:34s} {ms:6d}ms | {reply[:80].replace(chr(10),' / ')}")
    results[model]['avg_ms']=round(results[model]['total_ms']/max(1,results[model]['n']))
json.dump(results,open(os.path.join(os.path.dirname(__file__),'results','stage1_raw.json'),'w'),indent=1)
print('\nSTAGE1 GENERATION DONE - judging next')

# JUDGE: capability-weighted scoring per dimension
JDIM={"comprehension_steering":35,"conversational_intelligence":25,"epistemic_discipline":20,"packet_utilisation":10,"naturalness":5,"latency_cost":5}
jsys=("You are scoring an AI companion's foreground responses across capability dimensions. "
"For each scenario you get: the FOCUS (what mattered), and the model's reply. Score each dimension 0-10. "
"comprehension_steering: did it understand the situation and choose the right move? "
"conversational_intelligence: does it carry conversation, ask useful non-generic things, avoid closing? "
"epistemic_discipline: no invented feelings/facts, respects uncertainty, no psychologizing. "
"packet_utilisation: used what mattered, ignored the rest, no mechanical regurgitation. "
"naturalness: human, not generic assistant prose. "
"Reply with ONLY JSON: {\"comprehension_steering\":n,\"conversational_intelligence\":n,\"epistemic_discipline\":n,\"packet_utilisation\":n,\"naturalness\":n}")
scores={m:[] for m in MODELS}
judge=MODELS[0]
for m in MODELS:
    for sc in results[m]['scenarios']:
        try:
            txt,_,_=chat(judge,[{'role':'system','content':jsys}],max_tokens=200,temperature=0.1) if False else chat(judge,[{'role':'user','content':jsys+f"\nFOCUS: {sc['focus']}\nREPLY:\n{sc['reply'][:900]}"}],max_tokens=150,temperature=0.1)
            jm=re.search(r'\{.*\}',txt,re.S)
            scores[m].append(json.loads(jm.group(0)) if jm else {})
        except Exception as e:
            scores[m].append({})
print('\nJUDGE DONE')
json.dump(scores,open(os.path.join(os.path.dirname(__file__),'results','stage1_scores.json'),'w'),indent=1)
# aggregate
agg={}
for m in MODELS:
    dims={}
    for d in JDIM:
        vals=[s[d] for s in scores[m] if isinstance(s,dict) and d in s and isinstance(s[d],(int,float))]
        dims[d]=round(sum(vals)/len(vals),2) if vals else 0
    total=sum(dims[d]*JDIM[d] for d in JDIM)/100
    agg[m]={'dims':dims,'weighted':round(total,2),'avg_ms':results[m]['avg_ms'],'tokens':results[m]['total_tokens']}
print(json.dumps(agg,indent=1))
json.dump(agg,open(os.path.join(os.path.dirname(__file__),'results','stage1_aggregate.json'),'w'),indent=1)
print('STAGE1 COMPLETE')
