#retrieve -> exlcude -> rank. Pure orchestration no HTTP no DB no parsing

from collections.abc import Collection

from common.config import PipelineConfig
from common.interfaces import RankingModule, RetrievalModule
from common.schemas import RankedResult , UserPreferenceState
from pipeline.selection import identity, select_restaurants

class RecommendationPipeline:
    def __init__ (
        self,
        retriever : RetrievalModule ,
        ranker : RankingModule ,
        config : PipelineConfig | None = None
    ):
        self._retriever = retriever
        self._rank = ranker
        self._config = config or PipelineConfig()
        
    def search (
        self ,
        state : UserPreferenceState ,
        top_k : int | None = None,
        exclude : Collection[str] = ()
    ):
        if top_k is None:
            top_k = self._config.ranking_top_k
        banned = set(exclude)
        
        #Over-fetch with the retrieval limit , so excluding still leaves enough
        # Bounded over-fetch counts dishes; the final limit counts restaurants.
        limit = min(1000, max(self._config.retrieval_top_k, top_k * 4))
        candidates = self._retriever(state , top_k = limit)
        
        #Filter before ranking so excluded restaurants never take a top_k slot
        kept = [c for c in candidates if c.restaurant_id not in banned]
        
        if not kept:
            return [];
        kept.sort(key=identity)
        ranked = self._rank(state, kept, top_k=len(kept))
        return select_restaurants(state, kept, ranked, top_k)

