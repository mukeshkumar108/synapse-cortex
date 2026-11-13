"""Guard: no new lexical interpretation of natural language.

A source line that builds a pattern out of three or more alternative English words ((a|b|c)) inside a regex call, or defines a word list for deciding what someone meant,
is a lexical heuristic. Existing ones are listed in lexical_allowlist.json (each is work still to be replaced, or a deterministic parser); the count per file may only go DOWN.
A new one fails this test. Parsing our own formats, ids, dates and protocols is fine and does not match (no run of three alternative words)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIRS = ["src"]
ALT = re.compile(r"\((?:\?:)?[A-Za-z' \-]{2,}(?:\|[A-Za-z' \-]{2,}){2,}\)")
REGEX_CALL = re.compile(r"\bre\.(?:compile|search|match|findall|sub|fullmatch|finditer|split)\(|\bcompile\(")
WORDLIST = re.compile(r"^\s*[A-Z_]*(?:WORDS|STOP|HINTS|TERMS|_ASKS?)\b\s*(?::[^=]+)?=")


def hits(path: Path) -> int:
    n = 0
    lines = path.read_text(errors="ignore").splitlines()
    for i, line in enumerate(lines):
        code = line.split("#", 1)[0]
        if WORDLIST.match(code):
            n += 1
        elif REGEX_CALL.search(code) and ALT.search(" ".join(l.split("#", 1)[0] for l in lines[i:i + 4])):      # the pattern may continue on the next lines
            n += 1
    return n


def current() -> dict:
    out = {}
    for d in SRC_DIRS:
        for p in sorted((ROOT / d).rglob("*.py")):
            if "tests" in p.parts or "labs" in p.parts or "scripts" in p.parts:
                continue
            n = hits(p)
            if n:
                out[str(p.relative_to(ROOT))] = n
    return out


ALLOW = Path(__file__).with_name("lexical_allowlist.json")


def test_no_new_lexical_interpretation():
    allowed = json.loads(ALLOW.read_text())
    grew = {f: (n, allowed.get(f, 0)) for f, n in current().items() if n > allowed.get(f, 0)}
    assert not grew, ("new word-list or word-alternation matching (file: found, allowed): " + json.dumps(grew) + ". Meaning comes from the model's structured output (Jev, the extractor), not from words. "
                      "If this is a deterministic parser of our own format, add it to lexical_allowlist.json with a reason in your commit.")


if __name__ == "__main__":
    ALLOW.write_text(json.dumps(current(), indent=1, sort_keys=True) + "\n")
    print("allowlist written:", sum(current().values()), "sites in", len(current()), "files")
