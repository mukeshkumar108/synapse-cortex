import httpx, json, sys

W = "llm-test-agent"
P = "user_5377a025-b876-4d1f-bd62-59352da44146"
token = None
if len(sys.argv) > 1:
    token = sys.argv[1]
else:
    import os
    token = os.environ.get("HONCHO_API_KEY", "")
H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
B = "http://honcho-api:8000/v3"


def show(label, r):
    try:
        body = r.json()
        print("==", label, r.status_code, json.dumps(body)[:1200])
    except Exception:
        print("==", label, r.status_code, r.text[:500])


with httpx.Client(timeout=90) as c:
    r = c.get(f"{B}/workspaces/{W}", headers=H); show("workspace get", r)
    r = c.get(f"{B}/workspaces/{W}/peers/{P}", headers=H); show("peer get", r)
    r = c.post(f"{B}/workspaces/{W}/search", headers=H, json={"query": "10k", "limit": 3}); show("workspace search", r)
    r = c.post(f"{B}/workspaces/{W}/peers/{P}/search", headers=H, json={"query": "10k", "limit": 3}); show("peer search", r)
    r = c.post(f"{B}/workspaces/{W}/peers/{P}/chat", headers=H, json={"query": "What is the user working toward?"}); show("peer chat", r)
    r = c.post(f"{B}/workspaces/{W}/peers/{P}/chat", headers=H, json={"query": "What is the user working toward?", "session_name": "main"}); show("peer chat w/session", r)
    r = c.get(f"{B}/workspaces/{W}/peers/{P}/representation", headers=H); show("representation", r)
    r = c.get(f"{B}/workspaces/{W}/peers/{P}/working-representation", headers=H); show("working-rep", r)
