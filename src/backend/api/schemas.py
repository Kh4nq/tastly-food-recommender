# HTTP contract. Shared AI types (form , state , previous result) are reused not coppied
from typing import Literal

from pydantic import Field, field_validator, model_validator

from backend.ports import User
from backend.services.auth_service import Registration
from backend.services.passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH

from backend.services.search_service import SearchCommand
from conversation.models import ConversationIntent
from common.schemas import (
    Location,
    PreviousResult,
    RankedResult,
    Schema,
    UserFormInput,
    UserPreferenceState,
    validate_known_constraint,
)

class SearchRequest(Schema):
    # Size limits protecct the paid AI call from oversize input
    message: str | None = Field(default = None , max_length = 500)
    form: UserFormInput = Field(default_factory = UserFormInput)
    preference_state: UserPreferenceState | None = None
    exclude_restaurant_ids: list[str] = Field(default_factory = list , max_length = 100)
    previous_results: list[PreviousResult] = Field(default_factory = list , max_length = 50)
    top_k : int = Field(default = 10 , ge = 1 , le = 50)
    include_map_places: bool = False
    defer_retrieval: bool = False

    @field_validator("preference_state")
    @classmethod
    def validate_preference_constraints(cls, state):
        if state is not None:
            for key, value in state.hard_constraints.items():
                validate_known_constraint(key, value)
            for key, value in state.soft_preferences.items():
                validate_known_constraint(key, value)
        return state
    
    def to_command(self , session_id : str) -> SearchCommand:
        return SearchCommand(
            session_id = session_id,
            form = self.form,
            preference_state = self.preference_state,
            message = self.message,
            previous_results = self.previous_results,
            exclude_restaurant_ids = self.exclude_restaurant_ids,
            top_k = self.top_k,
            include_map_places = self.include_map_places,
            defer_retrieval = self.defer_retrieval,
        )
        
class DishResult(Schema):
    restaurant_id: str
    menu_item_id: str | None = None
    dish_id: str | None = None
    rank: int
    score: float
    
    #Every thing below is optional: the frontend must cope with null
    restaurant_name: str | None = None
    dish_name: str | None = None
    address: str | None = None
    location: Location | None = None
    price_vnd : int | None = None
    price_is_verified: bool | None = None
    distance_km: float | None = None
    rating: float | None = None
    is_vegetarian : bool | None = None
    cuisine: str | None = None
    image_url: str | None = None
    review_count: int | None = None
    item_kind: str | None = None
    serving_style: str | None = None
    space_description: str | None = None
    space_tags: list[str] = Field(default_factory=list)
    space_source: str | None = None
    recommendation_group: Literal['primary', 'supplementary', 'general'] = 'general'
    food_match: float | None = None
    candidate_rank: int | None = None
    reason_features: dict = Field(default_factory=dict)
    eligible_menu_items: list[RankedResult] = Field(default_factory=list)
    # Retired feature: retain nullable fields for existing API consumers.
    explanation: str | None = None
    explanation_source: Literal['llm', 'deterministic'] | None = None
    catalog_only: bool = True
    
class MapPlace(Schema):
    id: str
    name: str
    dish: str = ''
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    distance_km: float | None = None
    price_vnd: int | None = None


class SearchResponse(Schema):
    session_id : str
    results : list[DishResult]
    state : UserPreferenceState
    clarification_required : bool
    warnings: list[str] = Field(default_factory=list)
    map_places: list[MapPlace] | None = None
    intent: ConversationIntent = "search"
    assistant_message: str | None = None
    retrieval_deferred: bool = False
    named_food_query: bool = False


# --- Accounts ---

#Loose shape checks only. The pattern text 
_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
_PHONE = r"^[0-9+()\-.\s]{8,20}$"
_NOT_BLANK = r"\S"

class RegisterRequest(Schema):
    role : Literal["customer" , "business"]
    full_name : str = Field(min_length = 1 , max_length = 100 , pattern = _NOT_BLANK)
    email: str = Field(max_length = 254, pattern = _EMAIL)
    password: str = Field(min_length = MIN_PASSWORD_LENGTH, max_length = MAX_PASSWORD_LENGTH)
    phone: str | None = Field(default = None, pattern = _PHONE)
    shop_name: str | None = Field(default = None, max_length = 100)
    

    @model_validator(mode = "after")
    def business_needs_a_shop(self) -> "RegisterRequest":
        if self.role == "business" and not (self.shop_name or "").strip():
            raise ValueError("shop_name is required for business accounts")
        return self


    def to_registration(self) -> Registration:
        return Registration(**self.model_dump())
    
    
class LoginRequest(Schema):
    # No minimum length : do no teach an attacker the password
    email: str = Field(min_length = 1, max_length = 254)
    password: str = Field(min_length = 1, max_length = MAX_PASSWORD_LENGTH)
    
    
class ChangePasswordRequest(Schema):
    current_password: str = Field(min_length = 1, max_length = MAX_PASSWORD_LENGTH)
    new_password: str = Field(min_length = MIN_PASSWORD_LENGTH, max_length = MAX_PASSWORD_LENGTH)

class UpdateProfileRequest(Schema):
    full_name: str = Field(min_length = 1, max_length = 100, pattern = _NOT_BLANK)
    phone: str | None = Field(default = None, pattern = _PHONE)
    shop_name: str | None = Field(default = None, max_length = 100)
    

class UserOut(Schema):
    # The only account shape that leaves the server: no hash, no counters
    id: str
    email: str
    full_name: str
    phone: str | None
    role: str
    shop_name: str | None

    @classmethod
    def from_user(cls, user: User) -> "UserOut":
        return cls(
            id = user.user_id,
            email = user.email,
            full_name = user.full_name,
            phone = user.phone,
            role = user.role,
            shop_name = user.shop_name,
        )

class AuthResponse(Schema):
    user: UserOut
