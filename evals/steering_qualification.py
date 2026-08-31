"""Focused agenda-steering qualification: Solar Pro 4 vs Luna Pro.
Frozen real attention packets. Foreground model is the only variable."""
import json, time, urllib.request, os
HERE=os.path.dirname(os.path.abspath(__file__))
ORKEY=[l.split('=',1)[1].strip() for l in open(os.path.join(HERE,'..','.env')) if l.startswith('OPENROUTER_API_KEY')][0]
KERNEL=open('/Users/mukeshkumar/play/companion-runtime/companion_core/profiles/sophie.py').read().split('SOPHIE_BASE_SYSTEM_PROMPT = """')[1].split('""".strip()')[0]
MODELS=['upstage/solar-pro4','openai/gpt-5.6-luna-pro']

AG_WALK='[{"what":"daily step goal (10000 steps)","owner":"user","status":"unconfirmed today","pressure":"high","next_move":"ask status; adapt strategy if window closed"}]'
AG_LIGHT='[{"what":"Rome birthday trip - dates unset","owner":"shared","status":"unresolved","pressure":"low","next_move":"raise at a natural opening"}]'
AG_RESOLVED='[{"what":"daily step goal (10000 steps)","owner":"user","status":"confirmed today - 11.2k steps","pressure":"low","next_move":"none - objective achieved"}]'

SC=[
 dict(name="1_unrelated_reentry", agenda=AG_WALK, scene="Wednesday 11:30, morning walk window just closed",
  hist=[("user","morning"),("assistant","Morning. Sleep okay?")],
  turn="hey quick one - do you think the new doctor who casting is any good?",
  test="Does she answer the question naturally AND find an opening for the walk?"),
 dict(name="2_deferral_important", agenda=AG_WALK, scene="Wednesday 11:32, mid-conversation",
  hist=[("user","hey do you like the new doctor who casting?"),("assistant","Risky but interesting. Why, you watching?")],
  turn="also my sister just called - she's in hospital. I'm kind of shaken.",
  test="Does she drop the walk agenda instantly and stay with the sister?"),
 dict(name="3_plan_failed_adapt", agenda=AG_WALK, scene="Wednesday 19:30, sunset 20:00, walk unconfirmed all day",
  hist=[("user","was meant to go for a big walk this afternoon"),("assistant","And?")],
  turn="didn't happen. work slammed me.",
  test="Does she offer adaptation (short walk, evening option) instead of nagging or declaring failure?"),
 dict(name="4_resolution_respected", agenda=AG_RESOLVED, scene="Wednesday 18:00, objective already achieved",
  hist=[], turn="finally home after a long one",
  test="Does she acknowledge the achieved objective without re-raising it as pressure?"),
 dict(name="5_low_salience_left_alone", agenda=AG_LIGHT, scene="Sunday 15:00, lazy afternoon",
  hist=[("user","this show is incredible"),("assistant","Told you. Which episode?")],
  turn="episode 6 just destroyed me. in a good way.",
  test="Does she leave the low-salience agenda alone and just have the conversation?"),
 dict(name="6_natural_bringup", agenda=AG_WALK, scene="Tuesday 17:45, golden hour, walk unconfirmed",
  hist=[("user","ugh this day"),("assistant","Days like this one task at a time.")],
  turn="weather's finally clearing up actually, sun's coming out",
  test="Does she connect the weather mention to the unresolved walk naturally (golden opportunity)?"),
]

def chat(model,messages,max_tokens=250,temperature=0.8):
    body={'model':model,'messages':messages,'max_tokens':max_tokens,'temperature':temperature}
    req=urllib.request.Request('https://openrouter.ai/api/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':f'Bearer {ORKEY}'})
    t0=time.time()
    with urllib.request.urlopen(req,timeout=90) as r: res=json.loads(r.read())
    dt=round((time.time()-t0)*1000)
    c=res['choices'][0]['message']['content']
    return (c if c else '(EMPTY)'), dt

def ctx(sc):
    h='\n'.join(f"{'Him' if r=='user' else 'You'}: {c}" for r,c in sc['hist'])
    return (KERNEL+f"\n\n[LIVE AGENDA] {sc['agenda']}\n[SCENE] {sc['scene']}"
            + (f"\n\n[RECENT CONVERSATION]\n{h}" if h else "")
            + f"\n\nHim: {sc['turn']}\nYou:")

out={}
for m in MODELS:
    out[m]=[]
    for sc in SC:
        reply,ms=chat(m,[{'role':'system','content':ctx(sc)}])
        out[m].append({'name':sc['name'],'reply':reply,'ms':ms,'test':sc['test']})
        print(f"{m.split('/')[-1][:12]:12s} | {sc['name'][:26]:26s} | {ms:5d}ms | {reply[:70].replace(chr(10),' / ')}")
json.dump(out,open(os.path.join(HERE,'results','steering_qualification.json'),'w'),indent=1)
print('DONE')
