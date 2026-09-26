"""Real elapsed time and SQL instrumentation; never records SQL parameters."""
from collections import Counter, defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
import math
import threading
import time
from sqlalchemy import event


def percentiles(values):
    values = sorted(values)
    return {f'p{p}': round(values[max(0, math.ceil(len(values)*p/100)-1)], 3) if values else 0
            for p in (50, 95, 99)}


class Metrics:
    def __init__(self, engine):
        self.context = ContextVar('synthetic_sql_stage', default=None)
        self.lock = threading.Lock()
        self.latencies = defaultdict(list)
        self.queries = defaultdict(list)
        self.sql_time = Counter()
        event.listen(engine, 'before_cursor_execute', self.before)
        event.listen(engine, 'after_cursor_execute', self.after)

    def before(self, conn, cursor, statement, params, context, many):
        context.synthetic_start = time.perf_counter()

    def after(self, conn, cursor, statement, params, context, many):
        state = self.context.get()
        if state:
            stage = state['stage']
            state['count'] += 1
            words = statement.lower().split()
            table = next((t for t in ('policy_decisions', 'rule_candidates', 'canonical_events',
                                      'policies', 'rules', 'companies', 'users', 'webhook_sources')
                          if t in words or t+'.id' in words), 'other')
            with self.lock:
                self.sql_time[stage+': '+words[0]+' '+table] += time.perf_counter()-context.synthetic_start

    @contextmanager
    def stage(self, name, mode):
        start = time.perf_counter()
        state = dict(stage=name, count=0)
        token = self.context.set(state)
        try:
            yield
        finally:
            with self.lock:
                self.latencies[mode+'.'+name].append((time.perf_counter()-start)*1000)
                self.queries[mode+'.'+name].append(state['count'])
            self.context.reset(token)

    def e2e(self, mode, start):
        with self.lock:
            self.latencies[mode+'.end_to_end'].append((time.perf_counter()-start)*1000)

    def report(self):
        combined = defaultdict(list)
        for key, values in self.latencies.items():
            combined[key.split('.')[1]].extend(values)
        return dict(latency_ms={k:dict(n=len(v), **percentiles(v)) for k,v in self.latencies.items()},
                    overall_latency_ms={k:dict(n=len(v), **percentiles(v)) for k,v in combined.items()},
                    service_sql={k:dict(min=min(v), max=max(v), mean=round(sum(v)/len(v), 3))
                                 for k,v in self.queries.items() if v},
                    sql_hotspots_seconds=[dict(category=k, seconds=round(v, 3))
                                          for k,v in self.sql_time.most_common(5)])
