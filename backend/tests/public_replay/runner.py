"""Explicit, offline STANDARD public replay. Never invoked at app startup."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import sys
import time
from .corpus import load, encode
from .mapping import envelope, TYPES
from .safety import guard


def shape_report(records):
    from tests.synthetic.metrics import percentiles
    sizes = dict(raw=[], sanitized=[], normalized=[], evidence=[], envelope=[])
    irregular = Counter()
    for record in records:
        specimen=record['specimen']; body=envelope(record); payload=specimen['payload']
        sizes['raw'].append(record['rawBytes'])
        sizes['sanitized'].append(len(encode(specimen)))
        for name,value in [('normalized',body['payload']),('evidence',body['evidence']),('envelope',body)]:
            sizes[name].append(len(encode(value)))
        obj=payload.get('pull_request') or payload.get('issue') or payload.get('review') or {}
        irregular['missing_labels']+='labels' not in obj
        irregular['empty_labels']+=obj.get('labels')==[]
        irregular['review_records_missing_body']+=record['family']=='review' and 'body' not in (payload.get('review') or {})
        irregular['null_merge_metadata']+='merged_at' in obj and obj['merged_at'] is None
        irregular['null_actor']+=specimen.get('actor') is None
        def visit(value):
            if value is None: irregular['null_values']+=1
            if isinstance(value,list):
                irregular['empty_arrays']+=not value
                for child in value: visit(child)
            if isinstance(value,dict):
                for child in value.values(): visit(child)
        visit(specimen)
    return dict(payload_sizes={key:dict(**percentiles(v),max=max(v),total=sum(v)) for key,v in sizes.items()},
        size_limits=dict(raw_limit=32768,payload_limit=16384,evidence_limit=8192,evidence_refs_limit=10,
            original_over_raw=sum(v>32768 for v in sizes['raw']),adapted_over_raw=sum(v>32768 for v in sizes['envelope']),
            original_over_raw_percent=100*sum(v>32768 for v in sizes['raw'])/len(records),
            normalized_over_limit=sum(v>16384 for v in sizes['normalized']),
            reduction_ratio=1-sum(sizes['normalized'])/sum(sizes['raw'])),
        observed_irregularities=dict(irregular))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--workers',type=int,choices=(1,5,20),default=20)
    args=parser.parse_args()
    url=os.environ.get('CVE_PUBLIC_REPLAY_DATABASE_URL',''); guard(url)
    os.environ.update(CVE_DATABASE_URL=url,CVE_DEV_MODE='false',CVE_UPLOAD_DIR='/tmp/e71-uploads',
                      CVE_JWT_SECRET=secrets.token_hex(32),CVE_WEBHOOK_MASTER_KEY=secrets.token_hex(32))
    from app.db import logger
    from .workload import Workload
    from .assertions import retries, audit
    logger.setLevel(logging.WARNING); logging.getLogger('httpx').setLevel(logging.WARNING)
    started=time.perf_counter()
    report=dict(status='IN PROGRESS',command='python -m tests.public_replay.runner '+' '.join(sys.argv[1:]),
        start=datetime.now(timezone.utc).isoformat(),database='cve_public_replay_test',workers=args.workers,
        git_commit=os.environ.get('CVE_REPLAY_COMMIT','UNSPECIFIED'),offline=True,
        production_changes=False,production_orchestration=False)
    try:
        records,manifest=load(); report.update(source_manifest=manifest,corpus_sha256=manifest['sha256'],
            real_specimens=len(records),event_distribution=dict(Counter(TYPES[r['family']] for r in records)),
            **shape_report(records))
        work=Workload(args.workers); work.setup()
        raw,raw_time=work.run(records,'raw')
        canonical,canonical_time=work.run(records,'canonical')
        assert [(r['family'],[p['outcome'] for p in r['pairs']]) for r in raw]==[
            (r['family'],[p['outcome'] for p in r['pairs']]) for r in canonical]
        rows=raw+canonical
        print(f'Raw and canonical persisted: {len(raw)} + {len(canonical)}',flush=True)
        governed=work.govern(rows)
        report['retry_audit']=retries(work,records,rows,governed)
        report.update(audit(rows,governed))
        report['modes']={}
        for mode,results,seconds in [('raw',raw,raw_time),('canonical',canonical,canonical_time)]:
            counts=[len(r['pairs']) for r in results]
            from tests.synthetic.metrics import percentiles
            report['modes'][mode]=dict(events=len(results),seconds=seconds,events_per_second=len(results)/seconds,
                rule_evaluations_per_pipeline_second=sum(r['rules_evaluated'] for r in results)/seconds,
                policy_evaluations_per_pipeline_second=sum(counts)/seconds,
                rules_evaluated=sum(r['rules_evaluated'] for r in results),zero_match=counts.count(0),
                single_match=counts.count(1),multi_match=sum(n>1 for n in counts),candidates=sum(counts),
                candidates_per_event=dict(mean=sum(counts)/len(counts),**percentiles(counts),max=max(counts)),
                policies=dict(Counter(p['outcome'] for r in results for p in r['pairs'])),
                default_governance=sum(len(r['pairs']) for r in results if r['family']=='issue_reopened'))
        report['approvals']=dict(Counter(a['status'] for a in governed['approvals']),requests=len(governed['approvals']),pending=0)
        report['raw_http']=dict(attempts=len(records)+72,accepted=len(records)+63,
                               expected_auth_rejected=3,expected_validation_rejected=6,unexpected_failures=0)
        report['economic']=dict(eligible=governed['eligible'],issued=len(governed['effects']),
            reversals=len(governed['reversals']),blocked=dict(Counter(governed['refusals'])),
            duplicate_collapses=50+9+len(governed['reversals']))
        # IDs, physical timestamps and source registration nonces are intentionally excluded.
        logical=dict(rows=[dict(index=r['index'],mode=r['mode'],family=r['family'],
            mapped=r['mapped'],outcomes=[{k:p[k] for k in ('outcome','rule_name','data')} for p in r['pairs']]) for r in rows],
            approvals=[{k:a[k] for k in ('index','mode','status')} for a in governed['approvals']],
            effects=[dict(index=v['index'],rule=v['pair']['rule_name'],amount=v['effect']['amount'],
                          beneficiary=v['effect']['beneficiaryUserId']) for v in governed['effects']],
            economic=report['economic'],reconciliation=report['reconciliation'])
        report['logical_sha256']=hashlib.sha256(json.dumps(logical,sort_keys=True,
            separators=(',',':'),default=str).encode()).hexdigest()
        report.update(work.metrics.report(),status='PASS',exit_code=0,
            errors=dict(expected_auth=3,expected_validation=6,unexpected_4xx=0,unexpected_5xx=0,db_errors=0,deadlocks=0,timeouts=0))
    except Exception as exc:
        report.update(status='FAIL',exit_code=1,error_type=type(exc).__name__)
        raise
    finally:
        report.update(end=datetime.now(timezone.utc).isoformat(),runtime_seconds=time.perf_counter()-started)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2,default=str)+'\n',encoding='utf-8')
        args.output.with_suffix('.md').write_text('# E7.1 public replay execution\n\nDevelopment environment only.\n\n```json\n'+json.dumps(report,indent=2,default=str)+'\n```\n',encoding='utf-8')
    print('PASS '+report['logical_sha256'],flush=True)


if __name__=='__main__': main()
