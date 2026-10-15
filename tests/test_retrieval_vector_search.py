import numpy as np
import pandas as pd
from retrieval.vector_search import score_candidates

def test_weighted_cosine_score():
    c=pd.DataFrame([{'restaurant_id':'r1','dish_id':'d1','menu_item_id':'m1'}])
    rv=np.array([[1.,0.]],dtype=np.float32); dv=np.array([[0.,1.]],dtype=np.float32)
    ri=pd.DataFrame({'vector_row':[0],'food_place_id':['r1']}); di=pd.DataFrame({'vector_row':[0],'dish_id':['d1']})
    out=score_candidates(c,np.array([[0.,1.]],dtype=np.float32),rv,ri,dv,di,dish_weight=.75)
    assert np.isclose(out.loc[0,'semantic_score'],.75)
