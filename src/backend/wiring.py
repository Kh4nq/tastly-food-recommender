# Composition root: the only place that knows every concrete class
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

import ranking
import retrieval
from backend.adapters.ai2_conversation import Ai2ConversationAdapter
from backend.adapters.catalog_pg import PostgresCatalog
from backend.adapters.session_pg import PostgresSessionStore
from backend.api.deps import Services
from backend.api.presenter import DishPresenter
from backend.gate import Gate
from backend.services.pipeline import RecommendationPipeline
from backend.services.search_service import SearchService
from backend.settings import ROOT, Settings
from common.schemas import UserPreferenceState
from retrieval.retriever import retrieve_map_places
from database.connection import close_pool, get_pool


from datetime import timedelta
from backend.limits import HashGate , RateLimiter
from backend.adapters.auth_pg import PostgresAuthStore
from backend.services.auth_service import AuthService , AuthConfig

DATA = ROOT / "data"


@dataclass(frozen=True)
class Built:
    services: Services
    close: Callable[[], None]


def _ping_database(pool) -> None:
    with pool.connection(timeout=2) as conn:
        conn.execute("SELECT 1")


def build_services(settings: Settings) -> Built:
    pool = get_pool()  # raises a clear error when DATABASE_URL is missing
    pool.wait(timeout=10)  # fail fast when the database is unreachable
    pipeline = RecommendationPipeline(
        # Absolute paths: the AI default is relative to the working directory
        retriever=partial(
            retrieval.retrieve_candidates,
            processed_dir=DATA / "processed",
            embeddings_dir=DATA / "embeddings",
        ),
        ranker=ranking.rank_candidates,
    )
    if settings.warmup:
        # First call loads datasets, the embedding model and the ranking model.
        # A food term makes retrieval embed text, so a missing model fails here, not for a user
        pipeline.search(UserPreferenceState(session_id="warmup", food=["pho"]), top_k=1)
        
    auth_store = PostgresAuthStore(pool) # same pool as search : one connection budget
    auth_service = AuthService(
        auth_store,
        auth_store ,
        AuthConfig (
            session_ttl = timedelta(days = settings.auth_session_days),
            max_failures = settings.auth_max_failures,
            lock_for = timedelta(minutes = settings.auth_lock_minutes)
        )
    )    
    
    services = Services(
        search_service=SearchService(
            PostgresSessionStore(pool), Ai2ConversationAdapter(), pipeline,
            map_finder=partial(retrieve_map_places, processed_dir=DATA / "processed", embeddings_dir=DATA / "embeddings"),
        ),
        presenter=DishPresenter(PostgresCatalog()),
        gate=Gate(settings.ai_concurrency, settings.ai_queue_timeout_s, settings.ai_timeout_s),
        health_checks={"database": lambda: _ping_database(pool)},
        auth_service = auth_service,
        hash_gate = HashGate(settings.auth_hash_concurrency, settings.auth_hash_queue_timeout_s),
        auth_limiter = RateLimiter(settings.auth_rate_burst, settings.auth_rate_per_minute)
    )
    return Built(services, close_pool)
