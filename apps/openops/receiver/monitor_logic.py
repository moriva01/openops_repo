"""Pure observation-time state transitions used by live monitoring and offline examples."""
SEVERITIES=['info','warning','minor','major','critical']

def next_state(monitor, value, observed):
    """Pure transition. Call only once per distinct, fresh, ordered observation."""
    state = monitor["state"]
    since = monitor["condition_since"]
    count = monitor["recovery_count"]
    gap = monitor["last_observed"] is not None and observed - monitor["last_observed"] > 60
    if gap:
        since, count = None, 0
    if value > monitor["threshold"]:
        count = 0
        if state in ("firing", "recovering"):
            return "firing", None, 0, None
        since = observed if since is None else since
        if observed - since >= monitor["duration_seconds"]:
            return "firing", None, 0, "opened"
        return "pending", since, 0, None
    if state in ("firing", "recovering"):
        count += 1
        if count >= monitor["recovery_samples"]:
            return "normal", None, 0, "resolved"
        return "recovering", None, count, None
    return "normal", None, 0, None


def severity_for(m,value):
    levels=m.get('thresholds') or [{'severity':m['severity'],'value':m['threshold']}]
    crossed=[v['severity'] for v in levels if (value>v['value'] if m.get('comparator','above')=='above' else value<v['value'])]
    return max(crossed,key=SEVERITIES.index) if crossed else None

