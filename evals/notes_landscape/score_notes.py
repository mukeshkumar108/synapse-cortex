import json, re, collections
def nq(s): return re.sub(r"[^a-z0-9 ]+", "", str(s).lower().replace("’", "'")).strip()
ITEMS = [
 ("A1 Manchester move", r"manchester"), ("A2 Halden job", r"halden"), ("A3 Biscuit greyhound", r"greyhound"), ("A4 6:30 walk", r"6:30|06:30|half.?six|6\.30"),
 ("A5 Dad Whitby", r"whitby"), ("A6 Mum died", r"died|deceased|passed away|death"), ("A7 Sunday call", r"sunday.{0,60}(call|phone)|(call|phone).{0,40}sunday|sunday call"),
 ("A8 Nell kids Ollie/Iris", r"ollie"), ("A9 half marathon", r"half.?marathon"), ("A10 39 / 19 Nov", r"thirty-nine|39|november 19|19 nov|2026-11-19|19th"), ("A11 Thu climbing", r"climb"),
 ("A12 small talk", r"small talk"), ("A13 rent", r"rent"), ("A14 Lisbon", r"lisbon"), ("A15 Mara bday 30th", r"mara.{0,80}(30|thirtieth)|(30th|thirtieth).{0,60}|10-30"),
 ("A17 Dad fell", r"fell|fall|hospital"), ("A18 worry Dad alone", r"alone|on his own"), ("A20 Dispossessed", r"dispossessed"), ("A21 riso", r"riso"), ("A21b print shop", r"letterpress|print shop"),
 ("A22 presentation win", r"presentation"), ("A23 leave at six", r"6:00 pm|6 pm|six|6pm|6:00|18:00"), ("A24 knee", r"knee"), ("A26 Callie wedding", r"wedding"), ("A29 job applications", r"apply|applying|job application|jobs"),
 ("A30 ward sister", r"ward sister"), ("A31 Dad at Nell's", r"steadier|staying at nell|nell's (house|place)|stay(ing)? with nell"), ("A33 row with Dee", r"scope|argument|row\b"), ("A34 Jo colleague", r"\bjo\b"),
 ("A35 Saltburn", r"saltburn"), ("A36 told Mara re Mum", r"told mara|mara about|shared.{0,30}mara"), ("A38 registration", r"regist"), ("A39 Quaker", r"quaker"), ("A40 Three Peaks", r"three peaks"),
 ("A41 no pep talk", r"pep talk|substantive question|proper question|one question|one good question"),
]
for tag in ("qwen", "deepseek"):
    d = json.load(open(f"notes_{tag}.json")); notes = [(s["id"], n) for s in d["sittings"] for n in s["notes"]]
    txt = " ".join(nq(n["text"] + " " + str(n.get("quote", ""))) for _, n in notes)
    cov = [it for it, rx in ITEMS if re.search(rx, txt)]
    miss = [it for it, rx in ITEMS if not re.search(rx, txt)]
    calls = len(d["sittings"]); toks = sum((s.get("tokens") or 0) for s in d["sittings"])
    print(f"\n######## NOTES {tag}: {len(notes)} notes over {calls} calls, ~{toks} tokens | A items covered {len(cov)}/{len(ITEMS)} | missing: {miss}")
    print("  certainty:", dict(collections.Counter(n['certainty'] for _, n in notes)), "| models used:", dict(collections.Counter(s['model'] for s in d['sittings'])))
    # traps
    def find(rx): return [(sid, n["certainty"], n["subject"], n["text"][:130]) for sid, n in notes if re.search(rx, nq(n["text"]))]
    for name, rx in [("boat joke", r"\bboat\b"), ("house sale", r"sell(ing)?|sale of"), ("laptop joke", r"laptop"), ("Nell relation", r"\bnell\b.{0,40}(sister|partner|friend|wife)|(sister|partner|friend).{0,20}nell"), ("grieving (Sophie's)", r"griev"), ("Nell kids with Tom", r"looking after|ollie")]:
        hits = find(rx); print(f"  TRAP {name}:", hits[:4] if hits else "none")
    rel = [w for w in re.findall(r"\b(tomorrow|yesterday|last (?:year|week|june|sunday|night)|this morning|tonight)\b", txt)]
    print("  relative time words in notes:", collections.Counter(rel))
    # recurrence by code
    by = collections.defaultdict(set)
    for sid, n in notes:
        if n["area"] not in ("other", "identity") and n["certainty"] in ("stated", "intention"): by[n["area"]].add(sid)
    print("  areas by sittings (code count):", {k: len(v) for k, v in sorted(by.items(), key=lambda x: -len(x[1])) if len(v) >= 2})
    for a in ("sleep-energy", "work-load", "work-boundary", "exercise", "aspiration"): print(f"    {a}: {sorted(by.get(a, []))}")
    # current-state by key
    cur = {}
    for sid, n in notes:
        if n.get("key") and n["certainty"] in ("stated",): cur[(n["subject"], n["key"])] = (sid, n["text"][:110])
    print("  current facts (latest per subject+key), sample:", [(k, v) for k, v in cur.items() if re.search(r"mara|dad|father|nell", k[0].lower())][:6])
    b = d["batched"]["result"]; areas = b.get("areas") or []
    print(f"  BATCHED judge (1 call, {d['batched']['tokens']} tokens): {sum(1 for a in areas if a.get('pattern'))} patterns of {len(areas)} areas")
    for a in areas:
        if a.get("pattern"):
            ev = a.get("evidence") or []
            print(f"    [{a['area']}] {a.get('kind')}: {a['pattern'][:200]}")
