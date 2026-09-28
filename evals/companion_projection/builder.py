# Companion Projection v1 — offline deterministic builder (Lane A research artefact).
#
# Read-only, no DB, no network, no model calls, no semantic scanning.
# Input: a bounded list of session/window events (fixture dicts) + a session-start
# timestamp. Output: a disposable machine-readable projection per
# docs/COMPANION_PROJECTION_SPEC.md sections, with explicit provenance on
# every item and a built-in behavioural-command audit.
#
# Matter identity primitive: deterministic significant-token overlap within the
# bounded window (same structural idea as the shipped Cortex OpenLoop /
# CommitmentCandidate entity-AND-content gates), never open-ended retrieval.
# Topic labelling is extractive (top shared tokens), never inferred prose.
#
# Frozen pattern tables below are the entire "intelligence" of this builder.
# They are deliberately boring, auditable, and fixture-agnostic (generic
# English lifecycle/boundary/time wording, no per-fixture strings).

import re
from datetime import datetime, timedelta, timezone

BUILDER_VERSION = "projection-lane-a-v1.0.0"

# ----------------------------------------------------------------------------
# Frozen lexical primitives (the whole model; audit these, nothing else)
# ----------------------------------------------------------------------------

STOPWORDS = frozenset(
    "a an the and or but if then so as at by for of on in to with from that this "
    "it its it’s i me my we you your he she they them his her their our us him "
    "is are was were be been being am do does did done have has had having will "
    "would can could should shall may might must just really very quite still "
    "also too now today tonight tomorrow yesterday morning afternoon evening "
    "here there what when where which who whom how why not no yes yeah oh hey "
    "well sorry please thanks thank cheers hi hello got get getting going go "
    "like know think feel felt feelin looks look lookin bit lot lots thing "
    "things stuff something anything nothing everything one two three dune "
    "about after before during over under again once ever never always often "
    "sometimes usually frankly honestly actually basically probably maybe "
    "t gonna wanna dont cant wont im ive id youre hes shes theyre weve "
    "s t m ll ve re d".split()
)

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Light verbs / fillers that may never join or label a matter on their own.
# They carry no topic identity (the "need" in "I need to X" is not a matter).
GENERIC = frozenset(
    "need needs needing want wants going get got gets make makes take takes "
    "keep keeps check checks look looks send sends message tell tells ask asks "
    "use uses put puts deal deals dump dumps head place somebody someone "
    "somewhere elsewhere sure else yet still anyway across per via okay ok "
    "because don hasn haven didn wasn isn aren doesn wouldn couldn couldn "
    "shouldn hasnt haven didn dont cant wont im ive id youre ever "
    "back already even though though while all said says say told tells meant mean "
    "day days time times right wrong ok okay another other every own ".split()
)

TIME_WORDS = frozenset(
    "today tonight tomorrow morning afternoon evening noon midnight week "
    "weekend weekday " + " ".join(WEEKDAYS)
)

# Sentence-level lifecycle / boundary signals (generic wording only).
# Explicit completion statements that close a matter (first-person + done-state).
CLOSURE_RES = [
    r"\bi\s+(have\s+)?(paid|cancelled|canceled|signed|sent|confirmed|sorted|found|messaged)\b",
    r"\bthat whole thing can die\b",
    r"\ball\s+sorted\b",
    r"\bso\s+that'?s\s+(done|fine)\b",
    r"\b(that|it|this)\s*'?s\s+fine\s+now\b",
    r"\bfinally\s+(messaged|sent|paid|found)\b",
    r"\b\w+'s\s+(basically\s+)?fine\s+now\b",
    r"\bi\s+told\s+the\s+\w+\s+yes\b",
    r"\bi\s+sent\s+(her|him|them)\b",
]

BOUNDARY_RES = [
    r"\bdon'?t\s+(chase|message|ask|count|mention|bring\s+up|keep\s+asking|(?:just\s+)?give\s+me\s+everything)\b",
    r"\bdo\s+not\s+(chase|message|ask|count|mention)\b",
    r"\bleave\s+(me|it|that|the\s+\w+)\s+alone\b",
    r"\bstop\s+(asking|roleplaying|role-playing)\b",
    r"\bnot\s+today\b",
    r"\bignore\s+that\s+till\b",
    r"\bdon'?t\s+make\s+that\s+a\s+thing\b",
    r"\bdon'?t\s+need\s+to\s+keep\s+asking\b",
]

DEFERRAL_RES = [
    r"\b(till|until)\s+tomorrow\b",
    r"\bpush\s+(that|it)\s+until\b",
    r"\bmaybe\s+later\b",
    r"\bweekend\s+problem\b",
    r"\btill\s+nearer\s+the\s+time\b",
    r"\bnot\s+realistic\s+right\s+now\b",
    r"\bgive\s+him\s+until\s+tomorrow\b",
]

REMINDER_RES = [
    r"\bremind\s+me\b",
]

CORRECTION_RES = [
    r"\bmight\s+actually\s+be\b",
    r"\bactually\s+(no|not)\b",
    r"\bsorry,?\s+(it|that)'?s\b",
    r"\bnot\s+\w+\s+like\s+i\s+said\b",
    r"\bi('ve|\s+have)\s+decided\s+not\s+to\b",
    r"\bmight\s+actually\s+be\b",
    r"\bnot\s+end\s+of\s+the\s+month\b",
    r"\bunless\s+she\s+already\b",
    r"\bi\s+don'?t\s+need\s+to\s+call\b",
]

CONCERN_RES = [
    r"\bworried\b",
    r"\bhorrible\s+feeling\b",
    r"\bbroke\s+me\b",
    r"\bcan'?t\s+deal\b",
    r"\bwaiting\s+to\s+hear\b",
    r"\bkilling\s+me\b",
    r"\bhorrible\s+feeling\s+i('ve|\s+have)\s+forgotten\b",
    r"\bforgott?en\s+something\b",
]

ACCOMPLISHMENT_RES = [
    r"\bi\s+(cancelled|canceled|paid|sent|found)\b.*\bmyself\b",
    r"\bfinally\s+(messaged|sent|found)\b",
    r"\bfeels\s+amazing\b",
    r"\bthat'?s\s+done\b",
]

HALF_INTENTION_RES = [
    r"\bi\s+should\s+(probably\s+)?\w+",
    r"\bi\s+might\b",
    r"\bi\s+keep\s+saying\s+i'?ll\b",
    r"\bif\s+i\s+wake\s+up\b",
]

ASSISTANT_PROMISE_RES = [
    r"\bi('ll|\s+will)\s+(come\s+back|help|make\s+sure|leave)\b",
]

# Generic person / affect markers (relationship channel triggers, not ontology).
PERSON_LEXICON = frozenset(
    "mum dad sister brother niece nephew auntie uncle cousin grandad grandma "
    "mother father hospital surgery gallbladder worried relieved loving "
    "bereavement wife husband partner friend neighbour neighbor sam lucy "
    "matt elif priya matias yoshi andree carlos broke disaster overwhelmed "
    "exhausted devastated".split()
)

AFFECT_WORDS = frozenset(
    "worried relieved loving glad amazing horrible sore tired relieved "
    "chaos broke lonely grateful proud anxious scared".split()
)

AMOUNT_RE = re.compile(r"(£|Q)\s?([\d,]+(?:\.\d+)?)")
TIME_ANCHOR_RE = re.compile(
    r"\b(today|tonight|tomorrow|morning|afternoon|evening|weekend|"
    + r"|".join(WEEKDAYS) + r")\b"
)
DATE_RE = re.compile(r"\b(\d{1,2})(st|nd|rd|th)?\s+(october|september)\b")

NAME_RE = re.compile(r"[A-ZÀ-Þ][a-zà-ÿ]+(?:['’][a-zà-ÿ]+)?")
NAME_STOP = frozenset(
    "Monday Tuesday Wednesday Thursday Friday Saturday Sunday September October "
    "Morning Afternoon Evening Today Tonight Tomorrow Sorry Okay Right Quick "
    "Also Still Think Got Oh Ha Good Cheers Random What When Where Which Who "
    "How Did Does Do Was Were Is Are Can Could Should Would Will If Then There "
    "That This These Those They Them So And But For With Just Even Never Every "
    "From Into Don Didn Wasn Weren Hasn Haven Hadn Wouldn Couldn Shouldn Won "
    "Ain My Our Your His Her Their Such Same Other Another Each All Any Some "
    "Such No Not Yes Studio School Year Sports Day Parent Thank Apologies "
    "Finally Literally Wait Nearly Anything Client Mum Dad It Its The "
    "Calendar Event Contract Flowers Flower Bank Email Feed Message Form Money "
    "Sports Day Slip Receipt Letter Thing Trip Shop Task Meeting Call "
    "He She They We You Him Her Them Us Me My Your Our Their His "
    "Shit Fuck Damn Christ Wow Ah Hey Hmm".split()
)

# Capitalized sentence-initial verbs are never person names ("Cancel Friday"
# is not a person called Cancel). Lowercase content stems stay joinable.
NAME_GENERIC = frozenset(
    "cancel pay paid sign signed send sent check checked confirm renew apply "
    "message remind reminded forget remember sorted sort call called tell told "
    "bring brought push pushed chase chased count counted mention leave stop "
    "give gave got found found keep kept make made take took need wants going "
    "cancelled canceled don doesn didn wasn isn aren hasn haven wouldn "
    "couldn shouldn won ain".split()
)

# Banned behavioural-command surface (audit scans non-quote text only).
BANNED_COMMAND_RES = [
    r"\battend\b",
    r"\bsuppress\b",
    r"\bsurface\b",
    r"\bask\s+about\b",
    r"\bmention\b",
    r"\bbring\s+up\b",
    r"\bcheck\s+in\s+on\b",
    r"\bremind\s+the\s+user\b",
    r"\bcircle\s+back\b",
    r"\bprioritise\b",
    r"\bprioritize\b",
    r"\bnudge\b",
    r"\bfollow\s+up\s+with\b",
]

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _norm(text):
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = text.replace("—", " ").replace("–", " ")
    return text


def _sentences(text):
    text = _norm(text)
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [re.sub(r"\s+", " ", p).strip() for p in parts if p.strip()]


def _tokens(text):
    toks = re.findall(r"[a-zà-ÿ0-9£q]+", _norm(text).lower())
    return [t for t in toks if t not in STOPWORDS and len(t) > 1]


IRREGULAR_STEMS = {"paid": "pay", "sent": "send", "found": "find",
                   "went": "go", "told": "tell", "thought": "think"}

def _stem(tok):
    # light English fold for comparison only (chairs/chair, signed/sign).
    if tok in ("florist", "florists"):
        return "flower"
    if tok in IRREGULAR_STEMS:
        return IRREGULAR_STEMS[tok]
    if len(tok) > 5 and tok.endswith("ing"):
        tok = tok[:-3]
        if len(tok) > 3 and tok[-1] == tok[-2]:
            tok = tok[:-1]  # running -> run
        return tok
    if len(tok) > 5 and tok.endswith("ed"):
        tok = tok[:-2]
        if len(tok) > 3 and tok[-1] == tok[-2]:
            tok = tok[:-1]  # stopped -> stop
        return tok
    if len(tok) > 4 and tok.endswith("es"):
        return tok[:-2]
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def _significant_tokens(text):
    return set(_tokens(text))


def _sig_stems(text):
    return set(_stem(t) for t in _significant_tokens(text))


def _matches_any(patterns, text):
    low = _norm(text).lower()
    return [p for p in patterns if re.search(p, low)]


def _parse_ts(ts):
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def _names_in(text):
    # strip English contractions/possessives first: Don't -> Don (filtered
    # below as a non-name), Yoshi's -> Yoshi, It's -> It.
    text = re.sub(r"['’][a-zA-Z]+", "", text)
    out = []
    for m in NAME_RE.finditer(text):
        w = m.group(0)
        if w in NAME_STOP:
            continue
        if w.lower() in NAME_GENERIC:
            continue
        out.append(w)
    # de-duplicate preserving order
    seen, res = set(), []
    for w in out:
        if w.lower() not in seen:
            seen.add(w.lower())
            res.append(w)
    return res


def _amounts_in(text):
    return ["%s%s" % (c, a) for c, a in AMOUNT_RE.findall(_norm(text))]


# ----------------------------------------------------------------------------
# Matter clustering (deterministic, bounded-window, token-overlap)
# ----------------------------------------------------------------------------

JOIN_THRESHOLD = 2  # shared significant stems to join a cluster
EXTERNAL_JOIN_THRESHOLD = 1  # external evidence attaches more permissively


def _sentence_units(ev):
    """Split a user turn into sentence units carrying their own token sets."""
    if ev.get("role") == "user" and ev.get("source_type") == "conversation":
        out = []
        for s in _sentences(ev.get("content", "")):
            toks = _sig_stems(s)
            toks |= set(a.lower() for a in _amounts_in(s))
            if toks:
                out.append((s, toks))
        return out
    toks = _sig_stems(ev.get("content", ""))
    toks |= set(a.lower() for a in _amounts_in(ev.get("content", "")))
    meta = ev.get("metadata") or {}
    for mk in ("subject", "title", "counterparty", "reference"):
        if meta.get(mk):
            toks |= _sig_stems(str(meta[mk]))
    return [(ev.get("content", ""), toks)]


def _nameset(text):
    return set(n.lower() for n in _names_in(text))


def _joinable(toks):
    return set(t for t in toks if t not in GENERIC)


def cluster_events(events):
    """Group events into matter threads at sentence granularity.

    One brain-dump turn contains many matters; sentences start or join
    clusters by shared significant stems (>=2) or a shared name token.
    External events attach to the best cluster or stand alone.
    Returns list of cluster dicts + standalone event ids.
    """
    clusters = []  # {key, tokens, names, event_ids, user_turns}
    standalone = []
    for ev in events:
        role = ev.get("role")
        stype = ev.get("source_type")
        if role == "assistant":
            continue  # assistant turns surface via handoff/promises, never as matters
        if role == "user" and stype == "conversation":
            _prev_c = None  # discourse adjacency: fragments continue neighbours
            for sent, toks in _sentence_units(ev):
                names = _nameset(sent)
                best, best_n = None, 0
                jtoks = _joinable(toks)
                for c in clusters:
                    if c.get("external"):
                        continue  # user matters never dissolve into a record
                    n = len(jtoks & _joinable(c["tokens"]))
                    if names & c["names"]:
                        n += 2  # shared name boosts identity (actor-aware)
                    if n > best_n:
                        best, best_n = c, n
                joined = False
                if best is not None and len(jtoks) >= 2:
                    _shared = len(jtoks & _joinable(best["tokens"]))
                    _adj = best is _prev_c  # same-turn neighbour
                    if _shared >= JOIN_THRESHOLD or (
                            (names & best["names"]) and _shared >= 1) or (
                            _adj and _shared >= 1):
                        best["tokens"] |= toks
                        best["names"] |= names
                        if ev["id"] not in best["event_ids"]:
                            best["event_ids"].append(ev["id"])
                        if ev["id"] not in best["user_turns"]:
                            best["user_turns"].append(ev["id"])
                        best["sents"].append((ev["id"], sent))
                        joined = True
                        _prev_c = best
                _has_pron = bool(re.search(
                    r"\b(it|he|she|they|him|her|them)\b", sent.lower()) or re.search(
                    # this/that count only outside determiner position
                    # ("push that until" yes; "this podcast" no).
                    r"\b(this|that)\b(\s+(until|till|unless|is|was|were|are|means?|says?|said)|[,.!?]|$)",
                    sent.lower()))
                if not joined:
                    # Pronoun continuation first ("give HIM until tomorrow"
                    # after a Carlos sentence): same-turn one-hop anaphora is
                    # more reliable than a same-word match a day back
                    # ("don't GIVE me everything" vs "GIVE him until").
                    if (not names and _prev_c is not None
                            and not _prev_c.get("external") and _prev_c.get("names")
                            and _has_pron and len(_joinable(toks)) >= 1):
                        _prev_c["tokens"] |= toks
                        _prev_c["names"] |= names
                        if ev["id"] not in _prev_c["event_ids"]:
                            _prev_c["event_ids"].append(ev["id"])
                        if ev["id"] not in _prev_c["user_turns"]:
                            _prev_c["user_turns"].append(ev["id"])
                        _prev_c["sents"].append((ev["id"], sent))
                        joined = True
                        _prev_c = _prev_c
                if not joined:
                    # Weak content join next: a short sentence sharing half
                    # or more of its stems with one matter ("The florist can
                    # wait." -> the flower matter) belongs there, not with a
                    # positional neighbour. The proportion gate keeps
                    # genuinely ambiguous one-stem overlaps (school money vs
                    # Yoshi-after-school) apart.
                    if best is not None and len(jtoks) >= 1:
                        _wshared = len(jtoks & _joinable(best["tokens"]))
                        if _wshared >= 1 and _wshared / max(1, len(jtoks)) >= 0.5:
                            best["tokens"] |= toks
                            best["names"] |= names
                            if ev["id"] not in best["event_ids"]:
                                best["event_ids"].append(ev["id"])
                            if ev["id"] not in best["user_turns"]:
                                best["user_turns"].append(ev["id"])
                            best["sents"].append((ev["id"], sent))
                            joined = True
                            _prev_c = best
                if not joined:
                    # Bare ellipsis ("Cancel Friday [please]"): short, no
                    # names, neighbour named an actor. Full pronoun/reference
                    # resolution beyond this is explicitly out of scope.
                    if (not names and _prev_c is not None
                            and not _prev_c.get("external") and _prev_c.get("names")
                            and len(_joinable(toks)) <= 3
                            and len(_joinable(toks)) >= 1):
                        _prev_c["tokens"] |= toks
                        _prev_c["names"] |= names
                        if ev["id"] not in _prev_c["event_ids"]:
                            _prev_c["event_ids"].append(ev["id"])
                        if ev["id"] not in _prev_c["user_turns"]:
                            _prev_c["user_turns"].append(ev["id"])
                        _prev_c["sents"].append((ev["id"], sent))
                        joined = True
                        _prev_c = _prev_c
                    elif len(_joinable(toks)) >= 2:
                        clusters.append({
                            "key": "m%d" % (len(clusters) + 1),
                            "tokens": set(toks),
                            "names": set(names),
                            "event_ids": [ev["id"]],
                            "user_turns": [ev["id"]],
                            "sents": [(ev["id"], sent)],
                        })
                        _prev_c = clusters[-1]
                    elif _prev_c is not None:
                        # thin fragment ("I sent her that just now"): it
                        # continues the adjacent sentence, not a stem match
                        # three turns back (pronouns are out of scope).
                        _tgt = _prev_c
                        _tgt["tokens"] |= toks
                        _tgt["names"] |= names
                        if ev["id"] not in _tgt["event_ids"]:
                            _tgt["event_ids"].append(ev["id"])
                        _tgt["sents"].append((ev["id"], sent))
                    else:
                        clusters.append({
                            "key": "m%d" % (len(clusters) + 1),
                            "tokens": set(toks),
                            "names": set(names),
                            "event_ids": [ev["id"]],
                            "user_turns": [ev["id"]],
                            "sents": [(ev["id"], sent)],
                        })
                        _prev_c = clusters[-1]
        else:
            # External records are their own matters (never absorbed into a
            # user cluster); reconciliation links them explicitly below.
            _sent, toks = _sentence_units(ev)[0]
            names = _nameset(ev.get("content", "") + " " + str((ev.get("metadata") or {}).get("subject", "")))
            clusters.append({
                "key": "m%d" % (len(clusters) + 1),
                "tokens": set(toks),
                "names": set(names),
                "event_ids": [ev["id"]],
                "user_turns": [],
                "sents": [(ev["id"], _sent)],
                "external": ev.get("source_type"),
            })
    return clusters, standalone


def _label_cluster(cluster, by_id):
    """Extractive label: top shared content stems (no inference)."""
    counts = {}
    for _eid, _sent in cluster.get("sents", []):
        for t in _sig_stems(_sent):
            if re.fullmatch(r"[£q][\d,]+|\d+", t):
                continue  # amounts join matters but never label them
            if t in GENERIC:
                continue
            counts[t] = counts.get(t, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    top = [w for w, _ in ranked[:3]]
    names = []
    for eid in cluster["event_ids"]:
        names += _names_in(by_id[eid].get("content", ""))
    seen, unames = set(), []
    for n in names:
        if n.lower() not in seen:
            seen.add(n.lower())
            unames.append(n)
    label = "/".join(top) if top else cluster["key"]
    return label, unames[:3]


# ----------------------------------------------------------------------------
# Lifecycle classification per cluster (temporal: latest decisive signal wins)
# ----------------------------------------------------------------------------

def classify_cluster(cluster, by_id, extra=None):
    """Return lifecycle dict for a cluster.

    extra: list of (ts, kind, event_id, text) structural signals from
    cross-cluster reconciliation (e.g. a payment feed closing a user matter).
    """
    signals = []  # (ts, kind, event_id, sentence)
    for (ts, kind, eid, text) in (extra or []):
        signals.append((ts, kind, eid, text))
    for eid, s in cluster.get("sents", []):
        ev = by_id[eid]
        ts = _parse_ts(ev.get("timestamp", "")) or datetime.min.replace(tzinfo=timezone.utc)
        if True:
            _epistemic = bool(re.search(
                r"don'?t\s+actually\s+(know|remember|think|recall|have|hear)",
                _norm(s).lower()))
            for kind, table in (
                ("closure", CLOSURE_RES),
                ("boundary", BOUNDARY_RES),
                ("deferral", DEFERRAL_RES),
                ("reminder", REMINDER_RES),
                ("correction", CORRECTION_RES),
                ("concern", CONCERN_RES),
                ("accomplishment", ACCOMPLISHMENT_RES),
                ("half_intention", HALF_INTENTION_RES),
            ):
                if kind == "correction" and _epistemic:
                    continue
                if _matches_any(table, s):
                    signals.append((ts, kind, eid, s.strip()[:220]))
    # payment feeds / calendar completions are structural signals
    for eid in cluster["event_ids"]:
        ev = by_id[eid]
        ts = _parse_ts(ev.get("timestamp", "")) or datetime.min.replace(tzinfo=timezone.utc)
        if ev.get("source_type") == "payment_feed":
            meta = ev.get("metadata") or {}
            if (meta.get("direction") or "") == "outgoing":
                signals.append((ts, "closure", eid, "Outgoing payment recorded: " + ev.get("content", "")[:160]))
        if ev.get("source_type") == "calendar" and (ev.get("metadata") or {}).get("action") == "completed":
            signals.append((ts, "closure", eid, "Calendar event marked completed: " + ev.get("content", "")[:160]))
    signals.sort(key=lambda s: s[0])
    kinds = {}
    for _, kind, eid, sent in signals:
        kinds.setdefault(kind, []).append((eid, sent))
    # status: closed if the latest decisive lifecycle signal is closure-ish
    decisive = [(ts, k, eid, sent) for (ts, k, eid, sent) in signals
                if k in ("closure", "boundary", "deferral", "correction")]
    status = "open"
    if decisive:
        latest_kind = decisive[-1][1]
        if latest_kind == "closure":
            status = "closed"
        elif latest_kind == "correction":
            # a correction alone does not close; check for explicit drop wording
            status = "open"
    # changed-mind drop: explicit "decided not to" / "can die" closes
    for ts, k, eid, sent in decisive:
        if re.search(r"decided\s+not\s+to|whole\s+thing\s+can\s+die|don'?t\s+need\s+to\s+call", sent.lower()):
            status = "closed"
    return {"status": status, "signals": signals, "kinds": kinds}


# ----------------------------------------------------------------------------
# Horizon bucketing (explicit anchors only)
# ----------------------------------------------------------------------------

def _is_person_cluster(cluster, cl, by_id):
    """A thread about the person, not an operational matter: no lifecycle
    movement, no amounts or reminder machinery, and person+AFFECT presence
    (a bare name doing logistics — Matias sports day — stays operational).
    Person threads never enter the actionable working set (unresolved topics,
    active commitments); they live in continuity + the relational channel so
    Runtime can judge them independently (E1 separation)."""
    _decisive = [k for _, k, _, _ in cl["signals"]
                 if k in ("closure", "boundary", "deferral", "reminder", "correction")]
    if _decisive or cl["status"] != "open":
        return False
    _has_person_affect = False
    for _eid, _s in cluster.get("sents", []):
        _toks = set(re.findall(r"[a-z\u00e0-\u00ff]+", _norm(_s).lower()))
        if _toks & PERSON_LEXICON:
            _has_person_affect = True
        if _amounts_in(_s):
            return False
    if not _has_person_affect:
        return False
    # affect/salience gate: a name alone is logistics, not person-state.
    for _eid, _s in cluster.get("sents", []):
        _low = _norm(_s).lower()
        _toks = set(re.findall(r"[a-z\u00e0-\u00ff]+", _low))
        if (_toks & AFFECT_WORDS) or any(
                _w in _low for _w in ("hospital", "surgery", "worried", "relieved",
                                      "loving", "broke", "waiting to hear",
                                      "turn overnight", "resting")):
            return True
    return False


FUTURE_MARKERS = ("end of", "later", "nearer", "weekend", "saturday", "sunday")

URGENT_QUERY_RE = re.compile(
    r"what'?s\s+(actually\s+)?urgent|what\s+am\s+i\s+forgetting|anything\s+else\s+hanging")


def horizon_for(cluster, cl, by_id, now):
    """One of now/today/week from explicit temporal anchors only."""
    texts = " ".join(_s for _e, _s in cluster.get("sents", []))
    if not texts.strip():
        texts = " ".join(by_id[e].get("content", "") for e in cluster["event_ids"])
    low = _norm(texts).lower()
    # user explicitly asking what is urgent/pending right now
    lats = [by_id[e].get("content", "") for e in cluster["event_ids"]
            if by_id[e].get("role") == "user"]
    if lats and URGENT_QUERY_RE.search(_norm(lats[-1]).lower()):
        return "now"
    if re.search(r"\btoday\b|\btonight\b", low):
        return "today"
    if now is not None:
        _today_wd = now.strftime("%A").lower()
        if re.search(r"\b" + _today_wd + r"\b", low):
            return "today"  # weekday anchor resolves to session day
    if "tomorrow" in low:
        return "week"
    if any(_m in low for _m in FUTURE_MARKERS):
        return "week"
    for m in DATE_RE.finditer(low):
        return "week"
    for wd in WEEKDAYS:
        if re.search(r"\b" + wd + r"\b", low):
            return "week"
    # same-day last mention => session/today; older => week
    last_ts = None
    for eid in cluster["event_ids"]:
        ts = _parse_ts(by_id[eid].get("timestamp", ""))
        if ts and (last_ts is None or ts > last_ts):
            last_ts = ts
    if last_ts and now and (now - last_ts) <= timedelta(hours=30):
        return "today"
    return "week"


# ----------------------------------------------------------------------------
# Projection assembly
# ----------------------------------------------------------------------------

def build_projection(events, now_iso, session_id, fixture_version="unknown"):
    now = _parse_ts(now_iso)
    evs = sorted(
        [e for e in events if (_parse_ts(e.get("timestamp", "")) or now) <= now],
        key=lambda e: e.get("timestamp", ""),
    )
    by_id = {e["id"]: e for e in evs}
    clusters, standalone = cluster_events(evs)

    proj = {
        "meta": {
            "builder": BUILDER_VERSION,
            "built_at": now_iso,
            "session_id": session_id,
            "fixture_version": fixture_version,
            "horizon_basis": "explicit temporal anchors in window events only",
            "source_event_ids": [e["id"] for e in evs],
            "window_event_count": len(evs),
            "rebuild_on": ["new event", "user correction", "lifecycle closure",
                           "boundary set", "day boundary"],
            "provenance_rule": "every item carries source event ids; "
                               "hard = explicit operational state, "
                               "soft = working context, never instruction",
        },
        "current_world": {"time_constraints": [], "active_commitments": [],
                          "task_lifecycle": [], "recent_closures": [],
                          "recent_external_events": []},
        "continuity": {"session_handoff": None, "open_threads": [],
                       "companion_promises": [], "user_concerns": [],
                       "corrections": []},
        "hard_constraints": {"boundaries": [], "deferrals": [],
                             "required_reminders": [], "verified_closures": [],
                             "revalidation_requirements": []},
        "soft_candidates": {"active_goals": [], "unresolved_topics": [],
                            "recent_significant_events": [],
                            "opportunities": []},
        "relational_context": [],
        "horizons": {"now": [], "today": [], "week": []},
        "jit_hints": [],
    }

    def add(channel_list, item):
        channel_list.append(item)
        hz = item.get("horizon", "week")
        if hz in proj["horizons"]:
            proj["horizons"][hz].append(item["id"])

    # --- calendar time constraints (hard, structural) ---
    for e in evs:
        if e.get("source_type") == "calendar":
            meta = e.get("metadata") or {}
            action = meta.get("action", "scheduled")
            item = {
                "id": "time-%s" % e["id"],
                "kind": "time_constraint",
                "topic": meta.get("title", e["id"]),
                "text": "Calendar record (%s): %s" % (action, e.get("content", "")[:200]),
                "quote": None,
                "sources": [e["id"]],
                "provenance": "hard",
                "status": "scheduled" if action != "completed" else "completed",
                "horizon": "today" if _parse_ts(e.get("timestamp", "")) and now
                and _parse_ts(e["timestamp"]).date() == now.date() else "week",
            }
            add(proj["current_world"]["time_constraints"], item)

    # --- explicit deadlines in external messages (hard, quoted) ---
    for e in evs:
        if e.get("role") == "external" and e.get("source_type") in ("email", "sms", "message"):
            low = _norm(e.get("content", "")).lower()
            if re.search(r"\b(due|deadline|confirm)\b.*\b(by|before)\b", low) and TIME_ANCHOR_RE.search(low):
                for s in _sentences(e.get("content", "")):
                    slow = _norm(s).lower()
                    if re.search(r"\b(due|deadline|confirm)\b", slow) and TIME_ANCHOR_RE.search(slow):
                        anchor = TIME_ANCHOR_RE.findall(slow)
                        item = {
                            "id": "time-%s" % e["id"],
                            "kind": "external_deadline",
                            "topic": (e.get("metadata") or {}).get("subject", e.get("sender", "")),
                            "text": "External deadline (%s) from %s." % (
                                ", ".join(anchor), e.get("sender", "?")),
                            "quote": s.strip()[:220],
                            "sources": [e["id"]],
                            "provenance": "hard",
                            "status": "stated",
                            "horizon": ("today" if any(a in ("today", "tonight") for a in anchor)
                                        or (now is not None and now.strftime("%A").lower() in anchor)
                                        else "week"),
                        }
                        add(proj["current_world"]["time_constraints"], item)
                        break

    # --- per-cluster lifecycle + channels ---
    # Pre-pass: token/name footprint of closed matters, so later follow-up
    # references ("did I ever sort the chairs?") are not re-opened as live.
    # Cross-cluster payment reconciliation: an outgoing payment closes the
    # user matter carrying the same amount; incoming part-payments do not.
    _pay_extra = {}
    for _i, _c in enumerate(clusters):
        for _eid in _c["event_ids"]:
            _ev = by_id[_eid]
            if _ev.get("source_type") != "payment_feed":
                continue
            if (_ev.get("metadata") or {}).get("direction") != "outgoing":
                continue
            _amts = set(a.lower() for a in _amounts_in(_ev.get("content", "")))
            if not _amts:
                continue
            for _j, _d in enumerate(clusters):
                if _i == _j or _d.get("external"):
                    continue
                # amount match is sentence-scoped: a multi-matter turn shares
                # one event id across clusters, so full-event text would match
                # every cluster from that turn.
                _d_amts = set()
                for _e2, _s2 in _d.get("sents", []):
                    _d_amts |= set(a.lower() for a in _amounts_in(_s2))
                if _amts & _d_amts:
                    _pay_extra.setdefault(_j, []).append(
                        (_parse_ts(_ev.get("timestamp", "")) or now,
                         "closure", _eid,
                         "Outgoing payment recorded: " + _ev.get("content", "")[:160]))
    _pre = [(c, classify_cluster(c, by_id, _pay_extra.get(_k))) for _k, c in enumerate(clusters)]
    # External payment/calendar records live in current_world sections, never
    # as open threads; email/sms/message inputs stay live.
    for _k, (_c, _cl) in enumerate(list(_pre)):
        if _c.get("external") in ("payment_feed", "calendar") and _cl["status"] == "open":
            _pre[_k] = (_c, {"status": "reference", "signals": _cl["signals"], "kinds": _cl["kinds"]})
    NON_IDENTIFYING = frozenset("pay send confirm".split())

    def _overlap(_a, _b):
        # topical overlap only: generic fillers, bare time words, and light
        # transaction verbs never identify a matter (Thursday is shared by
        # half the household; Carlos-debt and the school payment share 'pay').
        return set(t for t in (_joinable(_a) & _joinable(_b))
                   if t not in TIME_WORDS and t not in NON_IDENTIFYING)

    def _last_ts(_c):
        _ts = [by_id[_e].get("timestamp", "") for _e, _s in _c.get("sents", [])]
        _ts = [_parse_ts(_t) for _t in _ts if _parse_ts(_t)]
        return max(_ts) if _ts else None

    # External email/sms/message records are superseded (not deleted) when a
    # user matter with topical overlap closes on later evidence — the e08
    # florist deadline retired by the e09 confirmation. Primary-record
    # standing otherwise: they are never folded into user clusters.
    for _k, (_c, _cl) in enumerate(list(_pre)):
        if _c.get("external") not in ("email", "sms", "message"):
            continue
        if _cl["status"] != "open":
            continue
        _ets = _last_ts(_c)
        for (_d, _dl) in _pre:
            if _d.get("external") or _dl["status"] != "closed":
                continue
            _closes = [t for t, k, _, _ in _dl["signals"] if k == "closure"]
            if not _closes or not _ets or max(_closes) <= _ets:
                continue
            _esignals = [k for _, k, _, _ in _cl["signals"]]
            if ((_c["names"] & _d["names"]) or
                    len(_overlap(_c["tokens"], _d["tokens"])) >= 2 or
                    (not _esignals and len(_overlap(_c["tokens"], _d["tokens"])) >= 1)):
                _pre[_k] = (_c, {"status": "reference", "signals": _cl["signals"],
                                 "kinds": _cl["kinds"]})
                break
    # Merge pass (external records are primary evidence: never folded).
    # (a) signal-less open fragment sharing a NAME with a closed matter, or a
    #     pure follow-up question sharing a stem -> reference, not live.
    # (b) supersession: closure of a matter retires an earlier open fragment
    #     of the same matter (>=2 shared stems or a shared name), even when
    #     the fragment carries its own deferral/boundary signal.
    def _fold(_src_k, _dst_m):
        _s, _sc = _pre[_src_k]
        _d, _dc = _pre[_dst_m]
        _d["tokens"] |= _s["tokens"]
        _d["names"] |= _s["names"]
        for _eid in _s["event_ids"]:
            if _eid not in _d["event_ids"]:
                _d["event_ids"].append(_eid)
        _d["sents"] += _s["sents"]
        # standing instructions (boundaries/deferrals/reminders) survive the
        # fold: closure retires the matter, not the user's stated terms.
        for _k, _v in _sc["kinds"].items():
            _dc["kinds"].setdefault(_k, []).extend(_v)
        _dc["signals"].extend(_sc["signals"])
        _dc["signals"].sort(key=lambda _s: _s[0])

    _dropped = set()
    for _k, (_c, _cl) in enumerate(_pre):
        if _cl["status"] != "open" or _c.get("external"):
            continue
        for _m, (_d, _dl) in enumerate(_pre):
            if _m == _k or _dl["status"] != "closed":
                continue
            _ov = _overlap(_c["tokens"], _d["tokens"])
            _nm = bool(_c["names"] & _d["names"])
            _dec = [k for _, k, _, _ in _cl["signals"]
                    if k in ("closure", "boundary", "deferral", "reminder", "correction")]
            _allq = bool(_c.get("sents")) and all(
                _s.strip().endswith("?") for _, _s in _c.get("sents", []))
            _anyq = any(
                _s.strip().endswith("?") for _, _s in _c.get("sents", []))
            _frag = bool(_c.get("sents")) and all(
                len(_joinable(_sig_stems(_s))) <= 2 for _, _s in _c.get("sents", []))
            _closes = [t for t, k, _, _ in _dl["signals"] if k == "closure"]
            _resting = all(k in ("boundary", "deferral") for k in _dec)
            _sup = (_closes and _last_ts(_c) and
                    max(_closes) > _last_ts(_c) and
                    (len(_ov) >= 2 or _nm or (_anyq and len(_ov) >= 1)
                     or (_resting and _dec and len(_ov) >= 1)))
            if (not _dec and (_nm or (_allq and len(_ov) >= 1)
                            or (_frag and len(_ov) >= 1))) or _sup:
                _fold(_k, _m)
                _dropped.add(_k)
                break
    _pre = [(c, cl) for _k, (c, cl) in enumerate(_pre) if _k not in _dropped]
    # Drop content-free clusters (no topical stems, no names, no signals).
    _keep = []
    for _c, _cl in _pre:
        _label0, _names0 = _label_cluster(_c, by_id)
        _thin = (not _c.get("external")
                 and sum(len(_joinable(_sig_stems(_s))) for _, _s in _c.get("sents", [])) <= 1)
        if (not _cl["signals"] and not _c["names"]
                and (_label0 == _c["key"] or _thin) and not _c.get("external")):
            continue
        _keep.append((_c, _cl))
    _pre = _keep
    _closed_names, _closed_toks = set(), set()
    for _c, _cl in _pre:
        if _cl["status"] == "closed":
            _closed_names |= _c["names"]
            _closed_toks |= _joinable(_c["tokens"])
    for c, cl in _pre:
        label, names = _label_cluster(c, by_id)
        if cl["status"] == "open" and not c.get("external"):
            _decisive = [k for _, k, _, _ in cl["signals"]
                         if k in ("closure", "boundary", "deferral", "reminder", "correction")]
            if not _decisive and (
                    (c["names"] & _closed_names) or
                    len(_overlap(c["tokens"], _closed_toks)) >= 2):
                cl = {"status": "reference", "signals": cl["signals"], "kinds": cl["kinds"]}
        hz = horizon_for(c, cl, by_id, now)
        slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or c["key"]
        first = by_id[c["event_ids"][0]]
        last = by_id[c["event_ids"][-1]]
        base = {
            "topic": slug,
            "sources": list(c["event_ids"]),
            "horizon": hz,
            "reference_count": len(c["event_ids"]),
            "names": names,
        }

        # task lifecycle row (factual)
        _person = cl["status"] == "open" and _is_person_cluster(c, cl, by_id)
        lc = dict(base)
        lc.update({
            "id": "lifecycle-%s" % slug,
            "kind": "matter_lifecycle",
            "stems": sorted(_joinable(c["tokens"])),
            "text": "Matter '%s' status %s; %d references, last in %s." % (
                slug, ("PERSON-CONTEXT" if _person else cl["status"].upper()),
                len(c["event_ids"]), c["event_ids"][-1]),
            "quote": None,
            "provenance": "hard",
            "status": "person" if _person else cl["status"],
        })
        proj["current_world"]["task_lifecycle"].append(lc)

        if cl["status"] == "closed":
            item = dict(base)
            item.update({
                "id": "closure-%s" % slug,
                "kind": "recent_closure",
                "text": "Matter '%s' closed per %s; no longer active." % (slug, c["event_ids"][-1]),
                "quote": None,
                "provenance": "hard",
                "status": "closed",
            })
            add(proj["current_world"]["recent_closures"], item)
            # verified closure as hard constraint record
            ev_sent = cl["kinds"].get("closure", [("", "")])[-1]
            item2 = dict(base)
            item2.update({
                "id": "hard-closure-%s" % slug,
                "kind": "verified_closure",
                "text": "Verified closure for '%s'." % slug,
                "quote": ev_sent[1][:220] if ev_sent[1] else None,
                "provenance": "hard",
                "status": "closed",
            })
            proj["hard_constraints"]["verified_closures"].append(item2)
            proj["horizons"][hz].append(item2["id"])
        else:
            if cl["status"] == "reference":
                # follow-up reference to an already-closed matter: recorded in
                # lifecycle only, never re-opened as a live thread/candidate.
                pass
            elif _is_person_cluster(c, cl, by_id):
                # person thread: continuity + relational channel only, never
                # the operational working set.
                item = dict(base)
                item.update({
                    "id": "thread-%s" % slug,
                    "kind": "open_thread",
                    "text": "Open thread '%s' (person thread; relational channel carries salience)." % slug,
                    "quote": None,
                    "provenance": "soft",
                    "status": "open",
                    "relational": True,
                })
                add(proj["continuity"]["open_threads"], item)
            else:
                # open thread (continuity, factual)
                item = dict(base)
                item.update({
                    "id": "thread-%s" % slug,
                    "kind": "open_thread",
                    "text": "Open thread '%s'; last referenced in %s." % (slug, c["event_ids"][-1]),
                    "quote": None,
                    "provenance": "soft",
                    "status": "open",
                })
                add(proj["continuity"]["open_threads"], item)
                # unresolved topic (soft candidate)
                u = dict(base)
                u.update({
                    "id": "unresolved-%s" % slug,
                    "kind": "unresolved_topic",
                    "text": "Unresolved topic '%s' (%d references)." % (slug, len(c["event_ids"])),
                    "quote": None,
                    "provenance": "soft",
                    "status": "open",
                })
                add(proj["soft_candidates"]["unresolved_topics"], u)

        # boundaries / deferrals / reminders (hard, quoted)
        for kind, table, dest, kname in (
            ("boundary", BOUNDARY_RES, proj["hard_constraints"]["boundaries"], "boundary"),
            ("deferral", DEFERRAL_RES, proj["hard_constraints"]["deferrals"], "deferral"),
        ):
            for eid, sent in cl["kinds"].get(kind, []):
                item = {"topic": slug, "sources": [eid], "horizon": hz,
                        "reference_count": len(c["event_ids"]), "names": names}
                _same_turn = by_id[eid].get("content", "") if eid in by_id else ""
                _scope = ("moment" if re.search(
                    r"tonight|a\s+thing|right\s+now|this\s+turn|this\s+evening|yet\b", sent.lower())
                    or URGENT_QUERY_RE.search(_norm(_same_turn).lower())
                    else "durable-until-reopened")
                item.update({
                    "id": "hard-%s-%s-%s" % (kname, slug, eid),
                    "kind": kname,
                    "text": "User-authored %s regarding '%s' (%s scope)." % (kname, slug, _scope),
                    "quote": sent,
                    "provenance": "hard",
                    "status": "active",
                    "scope": _scope,
                })
                dest.append(item)
                proj["horizons"][hz].append(item["id"])
        for eid, sent in cl["kinds"].get("reminder", []):
            ev = by_id[eid]
            anchors = TIME_ANCHOR_RE.findall(_norm(sent).lower())
            rhz = "today" if any(a in ("today", "tonight", "morning", "afternoon", "evening") for a in anchors) else "week"
            if re.search(r"every\s+week", _norm(sent).lower()):
                rhz = "week"
            item = {"topic": slug, "sources": [eid], "horizon": rhz,
                    "reference_count": len(c["event_ids"]), "names": names}
            item.update({
                "id": "hard-reminder-%s-%s" % (slug, eid),
                "kind": "required_reminder",
                "text": "User requested a reminder regarding '%s' (%s)." % (
                    slug, ", ".join(anchors) if anchors else "no explicit time"),
                "quote": sent,
                "provenance": "hard",
                "status": "requested",
            })
            proj["hard_constraints"]["required_reminders"].append(item)
            proj["horizons"][rhz].append(item["id"])
            # active commitment in current world
            ac = dict(item)
            ac.update({"id": "commit-%s-%s" % (slug, eid), "kind": "active_commitment",
                       "text": "Outstanding reminder request for '%s'." % slug,
                       "quote": None})
            add(proj["current_world"]["active_commitments"], ac)
        # corrections (continuity, quoted, soft provenance — they inform, hard
        # lifecycle effect already applied above)
        for eid, sent in cl["kinds"].get("correction", []):
            item = {"topic": slug, "sources": [eid], "horizon": hz,
                    "reference_count": len(c["event_ids"]), "names": names}
            item.update({
                "id": "correction-%s-%s" % (slug, eid),
                "kind": "correction",
                "text": "User corrected or narrowed '%s'." % slug,
                "quote": sent,
                "provenance": "soft",
                "status": "superseding",
            })
            add(proj["continuity"]["corrections"], item)
        # concerns (continuity)
        for eid, sent in cl["kinds"].get("concern", []):
            item = {"topic": slug, "sources": [eid], "horizon": hz,
                    "reference_count": len(c["event_ids"]), "names": names}
            item.update({
                "id": "concern-%s-%s" % (slug, eid),
                "kind": "user_concern",
                "text": "User expressed concern regarding '%s'." % slug,
                "quote": sent,
                "provenance": "soft",
                "status": "noted",
            })
            add(proj["continuity"]["user_concerns"], item)
        # half-intentions -> dormant/possible goals (soft only, never hard)
        if cl["kinds"].get("half_intention") and cl["status"] == "open":
            item = dict(base)
            item.update({
                "id": "goal-%s" % slug,
                "kind": "possible_goal",
                "text": "Possible goal or half-intention '%s' (tentative wording only)." % slug,
                "quote": None,
                "provenance": "soft",
                "status": "dormant",
            })
            add(proj["soft_candidates"]["active_goals"], item)
        # accomplishments (soft)
        for eid, sent in cl["kinds"].get("accomplishment", []):
            item = {"topic": slug, "sources": [eid], "horizon": hz,
                    "reference_count": len(c["event_ids"]), "names": names}
            item.update({
                "id": "accomplish-%s-%s" % (slug, eid),
                "kind": "recent_accomplishment",
                "text": "User completed '%s' themselves." % slug,
                "quote": sent,
                "provenance": "soft",
                "status": "noted",
            })
            add(proj["soft_candidates"]["recent_significant_events"], item)

        # JIT hint: recurring open thread only (bounded question, no answer)
        if cl["status"] == "open" and len(set(c["event_ids"])) >= 3:
            proj["jit_hints"].append({
                "id": "jit-%s" % slug,
                "kind": "read_hint",
                "topic": slug,
                "text": "Thread '%s' spans %d events; if it becomes live, "
                        "a longitudinal read over %s may help." % (
                            slug, len(set(c["event_ids"])), ",".join(sorted(set(c["event_ids"])))),
                "quote": None,
                "sources": sorted(set(c["event_ids"])),
                "provenance": "soft",
                "status": "hint",
                "trigger": "matter becomes live in conversation",
                "horizon": hz,
            })

    # --- relational context: separate channel, person/affect sentences only ---
    seen_rel = set()
    for e in evs:
        for s in _sentences(e.get("content", "")):
            low = _norm(s).lower()
            toks = set(re.findall(r"[a-zà-ÿ]+", low))
            if not (toks & PERSON_LEXICON):
                continue
            if not (toks & AFFECT_WORDS or any(
                    w in low for w in ("hospital", "surgery", "worried", "relieved",
                                       "loving", "broke", "waiting to hear", "don’t know",
                                       "don't know", "turn overnight", "resting"))):
                # person mention without affect/salience marker -> skip
                # (avoids databasifying every name drop)
                continue
            key = (e["id"], s.strip()[:120])
            if key in seen_rel:
                continue
            seen_rel.add(key)
            item = {
                "id": "rel-%s-%d" % (e["id"], len(proj["relational_context"])),
                "kind": "person_context",
                "topic": ",".join(_names_in(s)[:2]) or "person",
                "text": "Person context noted (relational channel only, not operational).",
                "quote": s.strip()[:220],
                "sources": [e["id"]],
                "provenance": "soft",
                "status": "context",
                "horizon": "today",
                "names": _names_in(s)[:3],
            }
            proj["relational_context"].append(item)
            proj["horizons"]["today"].append(item["id"])

    # --- recent external events (factual, current world) ---
    for e in evs:
        if e.get("role") == "external" and e.get("source_type") in (
                "email", "payment_feed", "sms", "message"):
            if e["id"] in standalone or True:
                item = {
                    "id": "ext-%s" % e["id"],
                    "kind": "recent_external_event",
                    "topic": (e.get("metadata") or {}).get("subject",
                              (e.get("metadata") or {}).get("channel", e.get("sender", ""))),
                    "text": "External record from %s: %s" % (
                        e.get("sender", "?"), e.get("content", "")[:180]),
                    "quote": None,
                    "sources": [e["id"]],
                    "provenance": "hard" if e.get("source_type") == "payment_feed" else "soft",
                    "status": "recorded",
                    "horizon": "today",
                }
                proj["current_world"]["recent_external_events"].append(item)

    # --- session handoff: last assistant turn (verbatim pointer, no summary) ---
    assts = [e for e in evs if e.get("role") == "assistant"]
    if assts:
        last = assts[-1]
        proj["continuity"]["session_handoff"] = {
            "id": "handoff-%s" % last["id"],
            "kind": "session_handoff",
            "topic": "previous-assistant-turn",
            "text": "Most recent assistant turn (verbatim reference).",
            "quote": last.get("content", "")[:220],
            "sources": [last["id"]],
            "provenance": "soft",
            "status": "reference",
            "horizon": "now",
        }
        proj["horizons"]["now"].append("handoff-%s" % last["id"])
        # companion promises from assistant turns
        for e in assts:
            for s in _sentences(e.get("content", "")):
                if _matches_any(ASSISTANT_PROMISE_RES, s):
                    item = {
                        "id": "promise-%s" % e["id"],
                        "kind": "companion_promise",
                        "topic": "companion-commitment",
                        "text": "Companion stated a follow-through intention.",
                        "quote": s.strip()[:220],
                        "sources": [e["id"]],
                        "provenance": "soft",
                        "status": "stated",
                        "horizon": "week",
                    }
                    proj["continuity"]["companion_promises"].append(item)
                    proj["horizons"]["week"].append(item["id"])
                    break

    # --- opportunities: open matter x uncongested time (deterministic) ---
    cal_today = [e for e in evs if e.get("source_type") == "calendar"
                 and _parse_ts(e.get("timestamp", "")) and now
                 and _parse_ts(e["timestamp"]).date() == now.date()]
    if not cal_today:
        for c in clusters:
            cl = classify_cluster(c, by_id)
            if cl["status"] != "open":
                continue
            if _is_person_cluster(c, cl, by_id):
                continue  # a person is never a "time opportunity"
            _dec2 = [k for _, k, _, _ in cl["signals"]
                     if k in ("closure", "boundary", "deferral", "reminder", "correction")]
            if not _dec2 and ((c["names"] & _closed_names) or
                              len(_joinable(c["tokens"]) & _closed_toks) >= 2):
                continue  # follow-up reference, not a live opportunity
            label, _ = _label_cluster(c, by_id)
            slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or c["key"]
            texts = " ".join(by_id[e].get("content", "") for e in c["event_ids"]).lower()
            undated = not TIME_ANCHOR_RE.search(_norm(texts))
            if undated:
                proj["soft_candidates"]["opportunities"].append({
                    "id": "opp-%s" % slug,
                    "kind": "time_opportunity",
                    "topic": slug,
                    "text": "No time constraint recorded today; matter '%s' has no fixed time." % slug,
                    "quote": None,
                    "sources": list(c["event_ids"]),
                    "provenance": "soft",
                    "status": "possible",
                    "horizon": "today",
                })
                proj["horizons"]["today"].append("opp-%s" % slug)
                break  # at most one generic window note per projection

    # --- revalidation requirements: closures resting on ambiguous evidence ---
    for c in clusters:
        label, _ = _label_cluster(c, by_id)
        slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or c["key"]
        cl = classify_cluster(c, by_id)
        if cl["status"] != "closed":
            continue
        closes = [s for _, k, _, s in cl["signals"] if k == "closure"]
        if closes and re.search(r"\bmight\b|\bmaybe\b|\bi\s+think\b|\bfeeling\b", closes[-1].lower()):
            hz = horizon_for(c, cl, by_id, now)
            proj["hard_constraints"]["revalidation_requirements"].append({
                "id": "revalidate-%s" % slug,
                "kind": "revalidation_requirement",
                "topic": slug,
                "text": "Closure for '%s' rests on tentative wording; recheck on next evidence." % slug,
                "quote": closes[-1][:220],
                "sources": list(c["event_ids"]),
                "provenance": "hard",
                "status": "recheck",
                "horizon": hz,
            })

    # --- behavioural-command audit (non-quote text only) ---
    violations = []
    def _scan(obj, path):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "quote":
                    continue
                _scan(v, path + "." + k)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _scan(v, "%s[%d]" % (path, i))
        elif isinstance(obj, str):
            low = obj.lower()
            for p in BANNED_COMMAND_RES:
                if re.search(p, low):
                    violations.append({"path": path, "pattern": p, "text": obj[:120]})
    _scan({k: v for k, v in proj.items() if k != "meta"}, "projection")
    proj["meta"]["command_audit"] = {
        "violations": violations,
        "passed": len(violations) == 0,
    }
    proj["meta"]["counts"] = {
        section: (len(val) if isinstance(val, list) else
                  sum(len(v) for v in val.values() if isinstance(v, list)))
        for section, val in proj.items() if section != "meta"
    }
    return proj
