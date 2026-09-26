"""Stable logical data and an independent, deliberately non-DSL oracle."""
from dataclasses import dataclass, asdict
import hashlib
import json
import random

TYPES = ('internal.task.approved', 'internal.task.rejected',
         'external.customer.praise', 'external.repository.merged',
         'reward.redemption.created', 'reward.redemption.fulfilled', 'custom.signal.observed')
WEIGHTS = (35, 10, 15, 20, 5, 5, 10)
PROFILES = ('Conservative', 'Balanced', 'Automation-Friendly', 'Shadow-Oriented')
DECISIONS = ('ALLOW', 'REQUIRE_APPROVAL', 'SHADOW_ONLY', 'BLOCK')


@dataclass(frozen=True)
class Config:
    companies: int = 8
    users: int = 320
    events: int = 10000
    rules: int = 96
    policies: int = 96
    duplicate_rate: float = .07
    invalid_rate: float = .02
    webhook_rate: float = .10
    seed: int = 20260925
    workers: int = 20

    def __post_init__(self):
        if (self.companies < 2 or self.users % self.companies or
                self.users // self.companies < 5 or self.events < 100 or
                self.rules != self.companies * 12 or self.policies != self.companies * 12 or
                not 1 <= self.workers <= 50 or
                not .05 <= self.duplicate_rate <= .10 or
                not .01 <= self.invalid_rate <= .03 or not .10 <= self.webhook_rate <= 1):
            raise ValueError('Invalid synthetic configuration')

    @classmethod
    def smoke(cls, **kwargs):
        return cls(companies=4, users=60, events=500, rules=48, policies=48, **kwargs)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def generate(config):
    rng = random.Random(config.seed)
    types = [kind for kind, weight in zip(TYPES, WEIGHTS)
             for _ in range(config.events * weight // 100)]
    types += [TYPES[0]] * (config.events - len(types))
    rng.shuffle(types)
    raw = set(rng.sample(range(config.events), round(config.events * config.webhook_rate)))
    result = []
    for i, kind in enumerate(types):
        tenant = i % config.companies
        payload = dict(score=rng.randrange(101), trusted=rng.random() < .75,
                       risk=rng.randrange(100), route=rng.randrange(10),
                       team=rng.choice(['engineering', 'support', 'operations']),
                       logicalId=f'syn-{config.seed}-{i}')
        if i % 5:
            payload['reviewed'] = True
        result.append(dict(index=i, tenant=tenant, type=kind, payload=payload,
                           mode='raw' if i in raw else 'canonical',
                           occurredAt=1750000000000 + i * 1000 - (86400000 if i % 31 == 0 else 0)))
    return result


def condition(field, op, value):
    return dict(field=field, op=op, value=value)


def rule_specs():
    predicates = [('trusted', 'EQ', True), ('score', 'GT', 75), ('score', 'GTE', 50),
                  ('risk', 'LT', 30), ('risk', 'LTE', 60), ('team', 'IN', ['engineering', 'support']),
                  ('reviewed', 'EXISTS', True), ('trusted', 'NEQ', False),
                  ('score', 'GT', 95), ('risk', 'LT', 5), ('score', 'GTE', 0), ('score', 'GT', 110)]
    kinds = [0, 0, 0, 2, 3, 3, 4, 5, 2, 6, 1, 6]
    return [dict(name=f'Synthetic rule {j}', description='', active=True, priority=j,
                 eventType=TYPES[kinds[j]], conditions=[condition('payload.'+f, op, v)] +
                 [condition('payload.'+field, op2, val) for field,op2,val in
                  [('score','GTE',0), ('risk','LTE',100)][:j%3]],
                 outcome=dict(kind='INCENTIVE', data=dict(proposedReward=(j+1)*5, reasonCode='SYNTHETIC')))
            for j, (f, op, v) in enumerate(predicates)]


def expected_rules(event):
    # Explicit business cases, no production evaluator, field resolver or DSL interpreter.
    p = event['payload']
    tests = [p['trusted'], p['score'] > 75, p['score'] >= 50, p['risk'] < 30,
             p['risk'] <= 60, p['team'] in ('engineering', 'support'), 'reviewed' in p,
             p['trusted'], p['score'] > 95, p['risk'] < 5, p['score'] >= 0, False]
    kinds = [0, 0, 0, 2, 3, 3, 4, 5, 2, 6, 1, 6]
    return [j for j in range(12) if event['type'] == TYPES[kinds[j]] and tests[j]]


def policy_specs(profile):
    # Routes 0..7 select a profile baseline; 8 deliberately defaults; 9 creates all-four conflict.
    baseline = [
        ['REQUIRE_APPROVAL']*5 + ['BLOCK']*3,
        ['ALLOW']*4 + ['REQUIRE_APPROVAL']*3 + ['BLOCK'],
        ['ALLOW']*7 + ['REQUIRE_APPROVAL'],
        ['SHADOW_ONLY']*6 + ['ALLOW', 'REQUIRE_APPROVAL'],
    ][profile]
    specs = [dict(name=f'Synthetic policy {j}', description='', active=True, priority=j,
                  candidateKind='INCENTIVE', eventType=None,
                  conditions=[condition('event.payload.route', 'EQ', j)], decision=decision)
             for j, decision in enumerate(baseline)]
    for spec in specs:
        if spec['decision'] == 'ALLOW':
            spec['conditions'].append(condition('event.payload.trusted', 'EQ', True))
        if profile == 0:
            spec['conditions'].append(condition('candidate.data.proposedReward', 'GTE', 10))
        if spec['decision'] == 'SHADOW_ONLY':
            spec['conditions'].append(condition('event.sourceKind', 'EQ', 'INTERNAL'))
    for j, decision in enumerate(DECISIONS):
        specs.append(dict(name=f'Synthetic conflict {decision}', description='', active=True,
                          priority=8+j, candidateKind='INCENTIVE', eventType=None,
                          conditions=[condition('event.payload.route', 'IN', [9, j])], decision=decision))
    return specs


def expected_policies(event, rule_index):
    route = event['payload']['route']
    profile = event['tenant'] % 4
    baseline = (('REQUIRE_APPROVAL',)*5+('BLOCK',)*3,
                ('ALLOW',)*4+('REQUIRE_APPROVAL',)*3+('BLOCK',),
                ('ALLOW',)*7+('REQUIRE_APPROVAL',),
                ('SHADOW_ONLY',)*6+('ALLOW', 'REQUIRE_APPROVAL'))[profile]
    matches = [(route, baseline[route])] if route < 8 else []
    if matches and profile == 0 and (rule_index+1)*5 < 10:
        matches = []
    if matches and baseline[route] == 'ALLOW' and not event['payload']['trusted']:
        matches = []
    if matches and baseline[route] == 'SHADOW_ONLY' and event['mode'] != 'canonical':
        matches = []
    matches += [(8+j, decision) for j, decision in enumerate(DECISIONS) if route in (9, j)]
    matches.sort(key=lambda pair: (-DECISIONS.index(pair[1]), -pair[0]))
    return matches, matches[0][1] if matches else 'REQUIRE_APPROVAL'


def dataset_digest(config, events):
    return digest(dict(config={k:v for k,v in asdict(config).items() if k != 'workers'}, events=events))
