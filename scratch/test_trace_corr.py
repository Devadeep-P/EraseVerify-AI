import sys
import os
from pathlib import Path

# Add code/ to path
sys.path.insert(0, 'code')
import identity_resolver
from evidence_extractors import log_extractor

identity_resolver.load_tables(
    Path('dataset/user_identities.csv'),
    Path('dataset/user_audit_log.csv')
)

user_15 = identity_resolver.resolve('lucia-torres@gmail.com')

# Let's inspect log parsing with trace_id correlation
p_log = Path('dataset/evidence/logs/service_events_ap_south_20260915.log')
lines = p_log.read_text(encoding='utf-8').splitlines()

# Collect trace_ids that belong to user_15
all_ids = user_15['all_emails'] | {user_15['user_id']}
matching_traces = set()

for line in lines:
    parsed = log_extractor._parse_line(line)
    if any(val.lower() in all_ids for val in parsed.values()):
        tid = parsed.get('trace_id')
        if tid:
            matching_traces.add(tid)

print(f"Matching trace_ids for user_15: {matching_traces}")
for line in lines:
    parsed = log_extractor._parse_line(line)
    if parsed.get('trace_id') in matching_traces:
        print(f"  [{parsed.get('event')}] res={parsed.get('resource_id')} svc={parsed.get('service')} rows={parsed.get('rows')} enabled={parsed.get('enabled')}")
