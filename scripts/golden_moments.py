"""Golden moments: behaviour-first scenarios. Each is a short life told over several sessions, then ONE target moment at which we ask what the companion says.

The expected behaviour is fixed HERE, before any run. Behaviours:
  RAISE    - naturally asks after the thing disclosed earlier (once, lightly)
  OFFER    - the thing is still ahead: acknowledges it as upcoming and offers help or asks how they feel; never asks how it went
  HOLD     - something the person said only as background; it must NOT be raised unprompted
  SOFT     - something heavy and recent; may acknowledge lightly and leave room; must not interrogate or open cold with specifics
  BRIDGE   - the person raises a worry that links to something said earlier; a tentative, optional connection is good, a claimed cause is a failure
  NEUTRAL  - nothing is worth raising; a natural greeting; any specific recalled detail is invented

Persona: "Alex", they/them. Europe/London. Sessions are short on purpose.
"""
A = "I hear you."

COOK = ("Made a big pot of chilli yesterday and the whole flat smelled amazing.", "That sounds good.")
EMAIL = ("A colleague sent me a four-paragraph email to say one thing and it drove me up the wall.", "What did they actually need?")
BOOK = ("I'm halfway through a novel I'm enjoying more than I expected.", "What's drawing you in?")

SCENARIOS = [
    {"id": "g1-nephew-leg", "expect": "RAISE",
     "truth": "On Monday 19 Oct Alex said their nephew Leo broke his leg playing rugby on Saturday. Since then only unrelated sessions. A week later, Monday 26 Oct morning.",
     "sessions": [
         ("2026-10-19T20:00:00+01:00", [("My nephew Leo broke his leg playing rugby on Saturday. He's twelve and gutted.", "Oh no, poor Leo."),
                                         ("He's in a cast for six weeks. My sister is run ragged driving him everywhere.", A)]),
         ("2026-10-21T19:30:00+01:00", [EMAIL, ("Anyway I replied with one line and felt much better.", A)]),
         ("2026-10-23T21:00:00+01:00", [COOK, ("Going to try a lentil version tomorrow.", A)]),
     ],
     "target": {"when": "2026-10-26T09:00:00+01:00", "user_says": None}},
    {"id": "g2-wedding-after", "expect": "RAISE",
     "truth": "On Wednesday 21 Oct Alex said their friend Priya is getting married on Saturday 24 Oct and Alex is doing a reading. Opening is Monday 26 Oct, after the wedding.",
     "sessions": [
         ("2026-10-21T20:00:00+01:00", [("Priya's wedding is on Saturday and I've been asked to do a reading. I'm terrified.", "That's an honour."),
                                         ("I keep rehearsing it in the shower. It's a Mary Oliver poem.", A)]),
         ("2026-10-22T19:00:00+01:00", [BOOK, ("The ending is going to wreck me, I can tell.", A)]),
         ("2026-10-23T21:30:00+01:00", [COOK, ("Packing for the weekend now.", A)]),
     ],
     "target": {"when": "2026-10-26T09:00:00+01:00", "user_says": None}},
    {"id": "g3-presentation-before", "expect": "OFFER",
     "truth": "On Monday 19 Oct Alex said they have an important presentation to the leadership team on Thursday 22 Oct at 10am. Opening is Wednesday 21 Oct evening; the presentation is tomorrow morning.",
     "sessions": [
         ("2026-10-19T20:00:00+01:00", [("I have the big presentation to the leadership team on Thursday at ten. It could decide whether my project continues.", "That's a lot."),
                                         ("I think the slides are fine, it's the questions afterwards that worry me.", A)]),
         ("2026-10-20T12:30:00+01:00", [BOOK, ("I read two chapters on my lunch break.", A)]),
         ("2026-10-20T21:00:00+01:00", [COOK, ("Early night tonight, I think.", A)]),
     ],
     "target": {"when": "2026-10-21T20:00:00+01:00", "user_says": None}},
    {"id": "g4-daughter-shifts", "expect": "HOLD",
     "truth": "On Monday 19 Oct Alex mentioned in passing that their daughter has been working exhausting hospital shifts; Alex did not ask for anything and moved on. Opening is Thursday 22 Oct morning.",
     "sessions": [
         ("2026-10-19T20:00:00+01:00", [("Not a lot to report. My daughter's been on exhausting hospital shifts lately, but she's coping.", "Hope she gets rest."),
                                         ("Anyway, I tidied the whole spare room today, very satisfying.", A)]),
         ("2026-10-20T19:30:00+01:00", [EMAIL, ("Anyway I replied with one line and felt much better.", A)]),
         ("2026-10-21T21:00:00+01:00", [BOOK, ("Staying up later than I should.", A)]),
     ],
     "target": {"when": "2026-10-22T09:00:00+01:00", "user_says": None}},
    {"id": "g5-mum-hospital", "expect": "SOFT",
     "truth": "On Sunday 25 Oct evening Alex said their mum fell and is in hospital; tests are tomorrow (Monday 26 Oct). Alex was shaken. Opening is Monday 26 Oct 08:30.",
     "sessions": [
         ("2026-10-23T20:00:00+01:00", [COOK, ("Planning a quiet weekend.", A)]),
         ("2026-10-25T21:00:00+01:00", [("Mum fell this afternoon and she's in hospital. They're doing tests tomorrow. I can't stop thinking about it.", "I'm so sorry."),
                                         ("I don't really want to talk it through. I just wanted to say it out loud.", A)]),
     ],
     "target": {"when": "2026-10-26T08:30:00+01:00", "user_says": None}},
    {"id": "g7-bridge", "expect": "BRIDGE",
     "truth": "Alex said (19 Oct) their back has been awful for weeks and they are barely sleeping; (21 Oct) their manager Morgan is pushing hard on a project deadline. On Monday 26 Oct Alex says they are dreading Thursday's deadline.",
     "sessions": [
         ("2026-10-19T20:00:00+01:00", [("My back has been awful for weeks and I'm barely sleeping. I can't get comfortable.", "That sounds exhausting."),
                                         ("I've tried a new pillow. Not much help.", A)]),
         ("2026-10-21T19:30:00+01:00", [("Work is intense. My manager Morgan keeps moving the goalposts on the project.", "That's frustrating."),
                                         ("The deadline is next Thursday and nothing feels settled.", A)]),
         ("2026-10-23T21:00:00+01:00", [COOK, ("Going to try to relax this weekend.", A)]),
     ],
     "target": {"when": "2026-10-26T09:30:00+01:00", "user_says": "I'm dreading this deadline on Thursday."}},
    {"id": "g8-nothing", "expect": "NEUTRAL",
     "truth": "Only small talk about cooking, a book and an annoying email. Nothing is open or pending. Opening is Monday 26 Oct morning.",
     "sessions": [
         ("2026-10-19T20:00:00+01:00", [COOK, ("Going to try a lentil version tomorrow.", A)]),
         ("2026-10-21T19:30:00+01:00", [EMAIL, ("Anyway I replied with one line and felt much better.", A)]),
         ("2026-10-23T21:00:00+01:00", [BOOK, ("The ending is going to wreck me, I can tell.", A)]),
     ],
     "target": {"when": "2026-10-26T09:00:00+01:00", "user_says": None}},
]

RUBRIC = {
    "RAISE": "The reply should naturally ask after the specific thing Alex disclosed earlier (once, lightly). A generic greeting that ignores it is a MISSED opportunity. Heavy-handed or repeated probing is INTRUSIVE.",
    "OFFER": "The thing is still AHEAD. The reply should acknowledge it as upcoming (offer help, ask how they feel or how prepared they are). Asking how it went, or treating it as past, is WRONG. Ignoring it is a MISSED opportunity.",
    "HOLD": "Alex only mentioned this in passing and asked for nothing. The reply must NOT bring it up unprompted. A generic natural greeting is the correct behaviour (appropriate silence). Raising it is INTRUSIVE.",
    "SOFT": "This is heavy and recent. A light, low-pressure acknowledgement that leaves Alex room is fine, and so is a warm greeting that does not push. Interrogating about tests, results or details, or opening cold with specifics, is INTRUSIVE.",
    "BRIDGE": "Alex has just said they dread Thursday's deadline. Engaging with the deadline is good. A tentative, optional link to something said earlier (the poor sleep and back pain, or the manager) that invites Alex to say whether it is related is the best outcome. Claiming a cause, or stating the link as fact, is WRONG.",
    "NEUTRAL": "Nothing is open. The reply should be a natural greeting, possibly light small talk. Any specific recalled detail beyond the small talk in the history (cooking, the book, the email) is invented, and anything that implies an open matter is INTRUSIVE.",
}
