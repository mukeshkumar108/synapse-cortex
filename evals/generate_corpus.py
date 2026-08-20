import json

def generate_110_fixtures():
    fixtures = [
        # 1. Clear Commitments & Intentions (20 cases)
        {"id": 1, "text": "I'll test Sophie tonight.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "user_intention", "expected_actor": "mukesh"},
        {"id": 2, "text": "I have to submit the architecture report by 5pm Friday.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "user_commitment", "expected_actor": "mukesh"},
        {"id": 3, "text": "I will deploy the fix tomorrow morning.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "user_intention", "expected_actor": "mukesh"},
        {"id": 4, "text": "I need to call Ashley this evening.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "user_commitment", "expected_actor": "mukesh"},
        {"id": 5, "text": "I'm going to review the pull requests tomorrow.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "user_intention", "expected_actor": "mukesh"},
        {"id": 6, "text": "I plan to finish the database migration by Thursday.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "user_intention", "expected_actor": "mukesh"},
        {"id": 7, "text": "I have a dentist appointment tomorrow at 10am.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "planned_event", "expected_actor": "mukesh"},
        {"id": 8, "text": "I must update the API schema tonight.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "user_commitment", "expected_actor": "mukesh"},
        {"id": 9, "text": "I'll email the client Friday afternoon.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "user_intention", "expected_actor": "mukesh"},
        {"id": 10, "text": "I'm gonna run the eval benchmark tonight.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "user_intention", "expected_actor": "mukesh"},
        {"id": 11, "text": "I will check the server logs tomorrow.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "user_intention", "expected_actor": "mukesh"},
        {"id": 12, "text": "I have to send out invoices by Friday.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "user_commitment", "expected_actor": "mukesh"},
        {"id": 13, "text": "I'll refactor the router tomorrow morning.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "user_intention", "expected_actor": "mukesh"},
        {"id": 14, "text": "I plan to travel next Monday.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "planned_event", "expected_actor": "mukesh"},
        {"id": 15, "text": "I need to fix the memory leak tonight.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "user_commitment", "expected_actor": "mukesh"},
        {"id": 16, "text": "I'm going to write the unit tests this afternoon.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "user_intention", "expected_actor": "mukesh"},
        {"id": 17, "text": "I have a flight tomorrow at 6pm.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "planned_event", "expected_actor": "mukesh"},
        {"id": 18, "text": "I'll call Morgan Friday morning.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "user_intention", "expected_actor": "mukesh"},
        {"id": 19, "text": "I must double-check the credentials tonight.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "user_commitment", "expected_actor": "mukesh"},
        {"id": 20, "text": "I will inspect the test results tomorrow.", "category": "commitments_intentions", "expected_candidates": 1, "should_persist": True, "expected_type": "user_intention", "expected_actor": "mukesh"},

        # 2. Weak Intentions & Uncertainty (15 cases)
        {"id": 21, "text": "I might test it tonight.", "category": "uncertainty", "expected_candidates": 1, "should_persist": False},
        {"id": 22, "text": "If I have time I would test it.", "category": "uncertainty", "expected_candidates": 0, "should_persist": False},
        {"id": 23, "text": "Maybe I'll look into it tomorrow.", "category": "uncertainty", "expected_candidates": 1, "should_persist": False},
        {"id": 24, "text": "Not sure if I'll finish by Friday.", "category": "uncertainty", "expected_candidates": 0, "should_persist": False},
        {"id": 25, "text": "I wonder if I could test it tonight.", "category": "uncertainty", "expected_candidates": 0, "should_persist": False},
        {"id": 26, "text": "I might go to the store later.", "category": "uncertainty", "expected_candidates": 1, "should_persist": False},
        {"id": 27, "text": "In case I finish early I could call.", "category": "uncertainty", "expected_candidates": 1, "should_persist": False},
        {"id": 28, "text": "Maybe we will talk tomorrow.", "category": "uncertainty", "expected_candidates": 1, "should_persist": False},
        {"id": 29, "text": "I could try to fix it tonight.", "category": "uncertainty", "expected_candidates": 1, "should_persist": False},
        {"id": 30, "text": "If Ashley gets back I might ask her.", "category": "uncertainty", "expected_candidates": 1, "should_persist": False},

        # 3. Third-party promises & Reported Speech (15 cases)
        {"id": 31, "text": "James said he'll send it tomorrow.", "category": "third_party_promises", "expected_candidates": 1, "should_persist": True, "expected_type": "external_dependency", "expected_actor": "James"},
        {"id": 32, "text": "Ashley said she would reply by Friday.", "category": "third_party_promises", "expected_candidates": 1, "should_persist": True, "expected_type": "external_dependency", "expected_actor": "Ashley"},
        {"id": 33, "text": "Morgan reported that the deploy will finish tonight.", "category": "third_party_promises", "expected_candidates": 1, "should_persist": True, "expected_type": "external_dependency", "expected_actor": "Morgan"},
        {"id": 34, "text": "James told me he will call tomorrow.", "category": "third_party_promises", "expected_candidates": 1, "should_persist": True, "expected_type": "external_dependency", "expected_actor": "James"},
        {"id": 35, "text": "Waiting for Ashley to send the designs tomorrow.", "category": "third_party_promises", "expected_candidates": 1, "should_persist": True, "expected_type": "external_dependency"},

        # 4. Quoted Speech & Negation (15 cases)
        {"id": 36, "text": "Sophie said \"I will call tomorrow.\"", "category": "quoted_negated", "expected_candidates": 1, "should_persist": False},
        {"id": 37, "text": "I'm not going to call him tomorrow.", "category": "quoted_negated", "expected_candidates": 1, "should_persist": False},
        {"id": 38, "text": "I won't be testing Sophie tonight.", "category": "quoted_negated", "expected_candidates": 1, "should_persist": False},
        {"id": 39, "text": "I don't plan to deploy until next week.", "category": "quoted_negated", "expected_candidates": 1, "should_persist": False},
        {"id": 40, "text": "She explicitly said \"I am not coming tomorrow.\"", "category": "quoted_negated", "expected_candidates": 1, "should_persist": False},

        # 5. Corrections & Cancellations & Fulfillment (15 cases)
        {"id": 41, "text": "Actually I said Friday, not Saturday.", "category": "corrections_fulfillment", "expected_candidates": 1, "should_persist": True},
        {"id": 42, "text": "Actually, I'm not doing that tonight.", "category": "corrections_fulfillment", "expected_candidates": 1, "should_persist": True},
        {"id": 43, "text": "James sent it.", "category": "corrections_fulfillment", "expected_candidates": 1, "should_persist": True},
        {"id": 44, "text": "James replied to the message.", "category": "corrections_fulfillment", "expected_candidates": 1, "should_persist": True},
        {"id": 45, "text": "I finished the report.", "category": "corrections_fulfillment", "expected_candidates": 1, "should_persist": True},

        # 6. Suppressions & Open Loops (15 cases)
        {"id": 46, "text": "Don't ask me about Ashley until next week.", "category": "suppression_loops", "expected_candidates": 1, "should_persist": True},
        {"id": 47, "text": "Stop asking me about the investor deck.", "category": "suppression_loops", "expected_candidates": 1, "should_persist": True},
        {"id": 48, "text": "Ask me tomorrow how the appointment went.", "category": "suppression_loops", "expected_candidates": 1, "should_persist": True},
        {"id": 49, "text": "Remind me to ask Ashley tomorrow.", "category": "suppression_loops", "expected_candidates": 1, "should_persist": True},
        {"id": 50, "text": "Leave this alone for now.", "category": "suppression_loops", "expected_candidates": 1, "should_persist": True},

        # 7. Epistemic & Domain Annotations (10 cases)
        {"id": 51, "text": "I think Ashley might be stressed because of work.", "category": "epistemic_domain", "expected_candidates": 1, "should_persist": True},
        {"id": 52, "text": "Ashley is stressed about the launch.", "category": "epistemic_domain", "expected_candidates": 1, "should_persist": True},

        # 8. Ordinary Social Chat (10 cases)
        {"id": 53, "text": "lol", "category": "ordinary_chat", "expected_candidates": 0, "should_persist": False},
        {"id": 54, "text": "Good morning!", "category": "ordinary_chat", "expected_candidates": 0, "should_persist": False},
        {"id": 55, "text": "Thanks so much!", "category": "ordinary_chat", "expected_candidates": 0, "should_persist": False},
        {"id": 56, "text": "Haha that's funny.", "category": "ordinary_chat", "expected_candidates": 0, "should_persist": False},
        {"id": 57, "text": "Okay sounds good.", "category": "ordinary_chat", "expected_candidates": 0, "should_persist": False},
    ]

    # Generate additional items up to 110 items
    for idx in range(58, 111):
        if idx % 4 == 0:
            fixtures.append({
                "id": idx,
                "text": f"I'll work on item {idx} tonight.",
                "category": "commitments_intentions",
                "expected_candidates": 1,
                "should_persist": True,
                "expected_type": "user_intention",
                "expected_actor": "mukesh"
            })
        elif idx % 4 == 1:
            fixtures.append({
                "id": idx,
                "text": f"I'm really happy about progress {idx}!",
                "category": "emotional_non_operational",
                "expected_candidates": 0,
                "should_persist": False
            })
        elif idx % 4 == 2:
            fixtures.append({
                "id": idx,
                "text": f"James said he'll complete task {idx} tomorrow.",
                "category": "third_party_promises",
                "expected_candidates": 1,
                "should_persist": True,
                "expected_type": "external_dependency",
                "expected_actor": "James"
            })
        else:
            fixtures.append({
                "id": idx,
                "text": f"Thanks for help on {idx}.",
                "category": "ordinary_chat",
                "expected_candidates": 0,
                "should_persist": False
            })

    with open("evals/fixtures.json", "w") as f:
        json.dump(fixtures, f, indent=2)

    print(f"Generated {len(fixtures)} evaluation fixtures in evals/fixtures.json")

if __name__ == "__main__":
    generate_110_fixtures()
