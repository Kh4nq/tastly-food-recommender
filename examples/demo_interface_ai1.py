from common.schemas import Location, UserPreferenceState
from retrieval import retrieve_candidates

state=UserPreferenceState(session_id='ai1-demo',location=Location(lat=21.03,lon=105.85),food=['bún chay'],cuisine=['vietnamese'],hard_constraints={'budget_max':100000,'max_distance_km':5,'vegetarian':True},soft_preferences={'ít dầu':True},semantic_preferences=['thanh đạm'])
candidates=retrieve_candidates(state,50)
print(f'AI3 received {len(candidates)} candidates')
for item in candidates[:5]: print(item.model_dump())
print('NOTE: v2 menu prices are synthetic estimates.')
