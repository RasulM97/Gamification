"""python -m tests.synthetic.runner --preset standard --output /tmp/result.json"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import random
import secrets
import sys
import time
from .generator import Config, generate, expected_rules, dataset_digest
from .safety import guard


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=['smoke','standard'], default='smoke')
    parser.add_argument('--workers', type=int, default=20)
    parser.add_argument('--seed', type=int, default=int(os.environ.get('CVE_SYNTHETIC_SEED','20260925')))
    parser.add_argument('--output', required=True)
    parser.add_argument('--compare', help='Prior successful result from identical configuration')
    args = parser.parse_args()
    # No application imports, database connections or schema changes before this guard.
    url = os.environ.get('CVE_SYNTHETIC_DATABASE_URL', '')
    guard(url)
    os.environ['CVE_DATABASE_URL'] = url
    os.environ['CVE_WEBHOOK_MASTER_KEY'] = secrets.token_hex(32)
    os.environ['CVE_JWT_SECRET'] = secrets.token_hex(32)
    os.environ['CVE_DEV_MODE'] = 'false'
    from .workload import Workload
    from .audits import counts, business_state, invalid_slice, isolation, provenance, immutability
    from .reporting import summarize, markdown
    from app.db import engine, logger
    logger.setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    config = (Config.smoke if args.preset=='smoke' else Config)(seed=args.seed, workers=args.workers)
    report = dict(status='IN PROGRESS', config=asdict(config), preset=args.preset,
                  timestamp=datetime.now(timezone.utc).isoformat(), git_commit=os.environ.get('CVE_SYNTHETIC_COMMIT','UNSPECIFIED'),
                  command='python -m tests.synthetic.runner '+' '.join(sys.argv[1:]), database='cve_synthetic_test',
                  connection_pool=dict(size=10, max_overflow=5),
                  errors=dict(expected_rejections=0, unexpected_4xx=0, unexpected_5xx=0,
                              db_errors=0, deadlocks=0, timeouts=0))
    started = time.perf_counter()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        events = generate(config)
        report['dataset_digest'] = dataset_digest(config, events)
        work = Workload(config)
        work.setup()
        before = business_state()
        burst_event = next(e for e in events if e['mode']=='canonical' and len(expected_rules(e))==1)
        report['bursts'] = work.burst(burst_event)
        print('50-worker event/candidate/decision bursts PASS', flush=True)
        results, seconds = work.run(events)
        report.update(summarize(config, events, results, seconds))
        report.update(work.metrics.report())
        print(f'Pipeline complete: {len(results)} events in {seconds:.3f}s', flush=True)
        by_index = {r['index']:r for r in results}
        duplicate_events = random.Random(config.seed+2).sample(events, round(config.events*config.duplicate_rate))
        raw_duplicates = 0
        for event in duplicate_events:
            assert work.persist(event) == by_index[event['index']]['event_id']
            raw_duplicates += event['mode']=='raw'
        report['duplicates'] = dict(event_attempts=len(duplicate_events), deduped=len(duplicate_events),
            unexpected_rows=0, candidate_retries=50, decision_retries=50,
            burst_replay_retries=1)
        initial_counts = counts()
        report['invalid_categories'] = invalid_slice(work, events[0])
        report['errors']['expected_rejections'] = sum(report['invalid_categories'].values())+1
        assert counts()==initial_counts
        report['isolation'] = isolation(work, results)
        report['provenance'] = provenance(work, events, results)
        report['immutability'] = immutability(results)
        assert business_state() == before
        report['business_effects'] = 'NONE: all other business tables unchanged'
        report['database_rows'] = counts()
        assert report['database_rows']['canonical_events'] == config.events
        assert report['database_rows']['rule_candidates'] == report['overall']['candidates']
        assert report['database_rows']['policy_decisions'] == report['overall']['decisions']
        assert report['database_rows']['rules'] == config.rules and report['database_rows']['policies'] == config.policies
        assert all(v['count']>0 for v in report['overall']['decision_distribution'].values())
        assert report['profiles']['Conservative']['decision_distribution']['BLOCK']['percent'] > report['profiles']['Automation-Friendly']['decision_distribution']['BLOCK']['percent']
        assert report['profiles']['Automation-Friendly']['decision_distribution']['ALLOW']['percent'] > report['profiles']['Conservative']['decision_distribution']['ALLOW']['percent']
        assert report['profiles']['Shadow-Oriented']['decision_distribution']['SHADOW_ONLY']['count'] > 0
        for mode in ('canonical', 'raw'):
            assert report['service_sql'][mode+'.rules']['max'] <= 4
            assert report['service_sql'][mode+'.policies']['max'] == 6
        assert report['service_sql']['raw.persistence']['min'] == 4
        report['raw_webhook'] = dict(accepted=round(config.events*config.webhook_rate)+raw_duplicates,
            unique=round(config.events*config.webhook_rate), deduped=raw_duplicates,
            rejected=sum(v for k,v in report['invalid_categories'].items() if k not in ('invalid_rule','invalid_policy'))+1,
            unexpected_errors=0)
        report['event_attempts'] = config.events+len(duplicate_events)+50
        if args.compare:
            previous = json.loads(Path(args.compare).read_text())
            assert previous['status']=='PASS'
            for key in ('config','dataset_digest','logical_digest','overall','profiles','modes','duplicates','database_rows','raw_webhook'):
                assert report[key] == previous[key], f'Replay differs: {key}'
            report['clean_replay'] = 'PASS'
        else:
            report['clean_replay'] = 'NOT EXECUTED in this invocation; use --compare'
        try:
            import resource
            report['peak_process_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        except ImportError:
            report['peak_process_rss_kib'] = 'UNAVAILABLE'
        report['status'] = 'PASS'
    except Exception as exc:
        report['status'] = 'FAIL'
        report['failure_type'] = type(exc).__name__
        # Avoid serializing exception text, SQL params, credentials or raw envelopes.
        if 'HTTP 4' in str(exc): report['errors']['unexpected_4xx'] += 1
        if 'HTTP 5' in str(exc): report['errors']['unexpected_5xx'] += 1
        if hasattr(exc, 'orig'):
            report['errors']['db_errors'] += 1
            if getattr(exc.orig,'pgcode',None)=='40P01': report['errors']['deadlocks'] += 1
        if 'Timeout' in type(exc).__name__: report['errors']['timeouts'] += 1
        raise
    finally:
        report['runtime_seconds'] = time.perf_counter()-started
        report['exit_code'] = 0 if report['status']=='PASS' else 1
        output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        output.with_suffix('.md').write_text(markdown(report), encoding='utf-8')
        engine.dispose()
        print(f"{report['status']}: {output}; runtime={report['runtime_seconds']:.3f}s", flush=True)


if __name__ == '__main__':
    main()
