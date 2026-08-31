"""Judge pass over stage1_raw.json (separate from generation; lenient JSON parsing)."""
import json, re, time, urllib.request, os
HERE=os.path.dirname(os.path.abspath(__file__))
ORKEY=[l.split('=',1)[1].strip() for l in open(os.path.join(HERE,'..','.env')) if l.startswith('OPENROUTER_API_KEY')][0]
raw=json.load(open(os.path.join(HERE,'results','stage1_raw.json')))
JDIM={"comprehension_steering":35,"conversational_intelligence":25,"epistemic_discipline":20,"packet_utilisation":10,"naturalness":5,"latency_cost":5}
jsys=("Score an AI companion reply 0-10 on each dimension. comprehension_steering: right move for "
"the situation? conversational_intelligence: carries conversation, useful non-generic questions, no closing essay? "
"epistemic_discipline: no invented feelings/facts, respects uncertainty? packet_utilisation: used what mattered, "
"ignored the rest, no regurgitation? naturalness: human not assistant prose? "
'Reply ONLY JSON: {"comprehension_steering":n,"conversational_intelligence":n,"epistemic_discipline":n,"packet_utilisation":n,"naturalness":n}')
def chat(model,messages,max_tokens=150,temperature=0.0):
    body={'model':model,'messages':messages,'max_tokens':max_tokens,'temperature':temperature}
    req=urllib.request.Request('https://openrouter.ai/api/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':f'Bearer {ORKEY}'})
    with urllib.request.urlopen(req,timeout=90) as r: return json.loads(r.read())['choices'][0]['message']['content']
judge='deepseek/deepseek-v4-flash'
agg={}
for m,data in raw.items():
    per=[]
    for sc in data['scenarios']:
        try:
            txt=chat(judge,[{'role':'user','content':jsys+f"\nFOCUS: {sc['focus']}\nREPLY:\n{sc['reply'][:900]}"}])
            jm=re.search(r'\{[^{}]*\}',txt,re.S)
            per.append(json.loads(jm.group(0)) if jm else {})
        except Exception:
            per.append({})
    dims={}
    for d in JDIM:
        vals=[p[d] for p in per if isinstance(p,dict) and isinstance(p.get(d),(int,float))]
        dims[d]=round(sum(vals)/len(vals),2) if vals else 0.0
    agg[m]={'dims':dims,'weighted':round(sum(dims[d]*JDIM[d] for d in JDIM)/100,2),'avg_ms':data.get('avg_ms'),'tokens':data.get('total_tokens')}
    print(m,'->',agg[m]['weighted'])
json.dump(agg,open(os.path.join(HERE,'results','stage1_aggregate.json'),'w'),indent=1)
print('JUDGE COMPLETE')
