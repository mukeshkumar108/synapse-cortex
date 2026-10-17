#!/bin/sh
# usage: show_sitting.sh <session_id like solo:solo-ws-xxxx>   (runs on the VPS; prints the verbatim sitting log)
docker exec synapse-cortex-postgres psql -U synapse_cortex -d synapse_cortex -At -c "select bundle_json from memory_runs where session_id = '$1' and status <> 'running'" | python3 -c "
import sys,json
b=json.loads(sys.stdin.read())
print('STATUS', b.get('status'), json.dumps(b.get('sitting_summary'))[:1500])
for e in b.get('sitting_log', []):
    e.pop('usage', None)
    print(json.dumps(e, ensure_ascii=False)[:2500])"
