"""Counterfactual resolvers only. They consume trusted context absent from production.
These are not production services, migrations, authorization guards or benchmarks.
"""
TEAMS=('Engineering','Sales','Operations')
PROJECTS={'Alpha':{1,4,5,6,7,8},'Beta':{2,4,8,9,10},'Gamma':{3,5,10,11}}

def team(company,user,tick):
    if company in ('A','E') or user==0:return None
    if company=='D' and user==4 and tick>=2000:return 'Sales'
    return TEAMS[(user-1)%3] if user<4 else TEAMS[(user-4)%3]

def members(company,scope,tick):
    value=set(PROJECTS[scope])
    if company=='D' and scope=='Alpha' and tick>=3000:value=(value-{1,7})|{2,9}
    return value

def resolve(scenario,actual,model):
    kind=scenario['scopeKind'];operation=scenario['operation'];company=scenario['company']
    if operation=='invariant' or kind not in ('team','project'):return actual
    if kind=='project' and model=='B':return actual
    raw=scenario['actor']
    if ':' in raw:
        actor_company,raw=raw.split(':',1)
        if actor_company!=company:return False
    scope=scenario['scope'];user=int(raw);tick=scenario.get('tick',1000)
    if operation=='visibility':
        return user==0 or (team(company,user,tick)==scope if kind=='team' else user in members(company,scope,tick))
    if operation=='approval':
        manager=TEAMS.index(scope)+1 if kind=='team' else ('Alpha','Beta','Gamma').index(scope)+1
        if company=='D' and scope=='Alpha' and tick>=3000:manager=2
        return user in (0,manager) and user!=scenario.get('subject',4)
    if operation=='targeting':return scenario['eventScope']==scope
    if operation=='reporting':
        return team(company,user,scenario.get('eventTick',1000)) if kind=='team' else scenario['eventScope']
    if operation=='context':
        return not (company=='C' and scope=='Gamma' and tick>=3000)
    raise AssertionError(operation)
