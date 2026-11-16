from src.services import notes


def test_a_section_is_closed_only_by_its_marker_never_by_words_in_the_prose():
    page = ("**The ferry timetable**\n- Still working out why the last crossing moved; this has not been resolved.\n\n"
            "**Old theory about the lighthouse [closed]**\n- Dropped after the survey.\n\n"
            "**Why the baker changed hours**\n- Open question.")
    lines = notes.holding_lines(page)
    assert [l.split(":")[0] for l in lines] == ["- The ferry timetable", "- Why the baker changed hours"]
