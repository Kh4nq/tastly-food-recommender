from common.schemas import RankedResult, UserPreferenceState , Candidate
from backend.services.pipeline import RecommendationPipeline

#Fakes live in tests only
POOL = [
    Candidate(restaurant_id = f"R{i}" , menu_item_id = f"M{i}" , dish_id = f"D{i}" , distance_km = float(i))
    for i in range(20 , 0 , -1) # far -> near, so the ranker really has to sort
]

def fake_retrieve(state , top_k = 100):
    return POOL[:top_k]

def fake_rank(state , candidates , top_k = 10):
    nearest = sorted(candidates , key = lambda c : c.distance_km)[:top_k]
    return [
        RankedResult(restaurant_id = c.restaurant_id , 
                     menu_item_id = c.menu_item_id , 
                     dish_id = c.dish_id , 
                     rank = i,
                     score = 1 / (1 + c.distance_km),
        ) for i , c in enumerate(nearest , start = 1)
    ]
    
STATE = UserPreferenceState(session_id = "S1")
pipeline = RecommendationPipeline(retriever = fake_retrieve , ranker = fake_rank)

def test_search_ranks_and_keeps_ids():
    results = pipeline.search(STATE , top_k = 3)
    assert [r.restaurant_id for r in results] == ["R1" , "R2" , "R3"]
    assert [r.menu_item_id for r in results] == ["M1" , "M2" , "M3"]
    assert [r.rank for r in results] == [1 , 2 , 3]
    
def test_search_excludes_and_still_fills_top_k():
    results = pipeline.search(STATE , top_k = 3 , exclude = ["R1"])
    assert [r.restaurant_id for r in results] == ["R2" , "R3" , "R4"]
    assert [r.rank for r in results] == [1 , 2 , 3]