from common.schemas import Location, UserPreferenceState
from retrieval import retrieve_candidates
state=UserPreferenceState(session_id='ai1-demo',location=Location(lat=21.03,lon=105.85),food=['bún chay'],cuisine=['vietnamese'],hard_constraints={'budget_max':100000,'max_distance_km':5,'vegetarian':True},semantic_preferences=['thanh đạm'])
for c in retrieve_candidates(state,50)[:10]: print(c.model_dump())
