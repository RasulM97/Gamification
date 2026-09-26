"""Logical replay comparison excludes random storage IDs and measured timings."""
from collections import Counter
from .generator import PROFILES, DECISIONS, digest
from .metrics import percentiles


def distribution(results):
    candidates = [d for r in results for d in r['decisions']]
    rules = [len(r['decisions']) for r in results]
    policies = [d['matches'] for d in candidates]
    decisions = Counter(d['decision'] for d in candidates)
    return dict(events=len(results), candidates=len(candidates), decisions=len(candidates),
        decision_distribution={d:dict(count=decisions[d], percent=round(100*decisions[d]/max(1,len(candidates)),3)) for d in DECISIONS},
        rules=dict(zero=rules.count(0), single=rules.count(1), multi=sum(n>1 for n in rules),
                   average=sum(rules)/max(1,len(rules)), p95=percentiles(rules)['p95'], maximum=max(rules,default=0),
                   applicable=sum(r['applicable'] for r in results)),
        policies=dict(default=policies.count(0), default_percent=round(100*policies.count(0)/max(1,len(policies)),3),
                      single=policies.count(1), multi=sum(n>1 for n in policies),
                      average=sum(policies)/max(1,len(policies)), maximum=max(policies,default=0)))


def summarize(config, events, results, seconds):
    logical = [dict(index=r['index'], tenant=r['tenant'], applicable=r['applicable'],
                    decisions=[{k:d[k] for k in ('rule', 'decision', 'matches')} for d in r['decisions']])
               for r in sorted(results,key=lambda r:r['index'])]
    overall = distribution(results)
    return dict(logical_digest=digest(logical), overall=overall,
        profiles={name:dict(companies=sum(t%4==p for t in range(config.companies)),
                            **distribution([r for r in results if r['tenant']%4==p])) for p,name in enumerate(PROFILES)},
        modes={mode:distribution([r for r in results if r['mode']==mode]) for mode in ('canonical','raw')},
        event_types=dict(Counter(e['type'] for e in events)),
        sources=dict(Counter('GENERIC_WEBHOOK' if e['mode']=='raw' else 'INTERNAL' for e in events)),
        roles=dict(ADMIN=config.companies, MANAGER=config.companies*3, EMPLOYEE=config.users-config.companies*4),
        throughput_per_second=dict(events=len(results)/seconds, rule_evaluations=len(results)/seconds,
            policy_evaluations=overall['candidates']/seconds, end_to_end_logical_events=len(results)/seconds),
        pipeline_seconds=seconds)


def markdown(report):
    lines = ['# E5.1 synthetic execution', '', f"Status: {report['status']}", '',
             'Development measurements only; no production capacity claim.', '',
             f"Command: `{report['command']}`", '',
             f"Database: `{report['database']}`; exit: {report['exit_code']}; "
             f"runtime: {report['runtime_seconds']:.3f}s.", '',
             f"Baseline: `{report['git_commit']}`; UTC: {report['timestamp']}.", '',
             f"Configuration: `{report['config']}`", '']
    if 'overall' not in report:
        return '\n'.join(lines)
    o = report['overall']
    lines += [f"Events: {o['events']}; candidates/decisions: {o['candidates']}.", '',
              '| Profile | Companies | Events | Candidates | ALLOW | APPROVAL | SHADOW | BLOCK |',
              '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for name, value in report['profiles'].items():
        counts = [str(value['decision_distribution'][d]['count']) for d in DECISIONS]
        lines.append(f"| {name} | {value['companies']} | {value['events']} | {value['candidates']} | "+' | '.join(counts)+' |')
    lines += ['', '| Stage | p50 ms | p95 ms | p99 ms |', '| --- | ---: | ---: | ---: |']
    for name, value in report.get('overall_latency_ms', {}).items():
        lines.append(f"| {name} | {value['p50']} | {value['p95']} | {value['p99']} |")
    for key in ('throughput_per_second', 'rules', 'policies', 'duplicates', 'errors',
                'isolation', 'provenance', 'immutability', 'database_rows', 'raw_webhook',
                'clean_replay', 'sql_hotspots_seconds'):
        lines += ['', f"**{key}:** `{report.get(key, o.get(key, 'unavailable'))}`"]
    lines += ['', 'Full mode/profile percentages, SQL counts and raw measurements are in the sibling JSON.']
    return '\n'.join(lines)
