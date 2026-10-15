"""Conservative benchmark admission control; never a provider-side spending cap."""
from decimal import Decimal, InvalidOperation


class BudgetExceeded(RuntimeError):
    pass


def amount(value):
    try:
        value = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Invalid monetary limit") from None
    if not value.is_finite() or value < 0:
        raise ValueError("Monetary limits must be finite and nonnegative")
    return value


class BudgetLedger:
    """Reserve before every attempt. Missing/failed billing keeps the reservation.

    Retry disabled in benchmark adapters. Actual charges exceeding a reservation
    stop subsequent calls, but cannot undo a bill already issued by the provider.
    """

    def __init__(self, max_calls=3, budget_usd="1", reserve_usd="0.10"):
        if type(max_calls) is not int or max_calls < 1:
            raise ValueError("max_calls must be a positive integer")
        self.max_calls = max_calls
        self.limit, self.reserve = amount(budget_usd), amount(reserve_usd)
        if self.limit == 0 or self.reserve == 0:
            raise ValueError("Budget and per-request reservation must be positive")
        self.calls = 0
        self.charged = Decimal(0)
        self.known_actual = Decimal(0)
        self.unknown_cost_calls = 0
        self.valid_responses = 0
        self.pending = False

    def admit(self):
        if self.pending:
            raise RuntimeError("Previous request must be settled before another admission")
        if self.calls >= self.max_calls or self.charged + self.reserve > self.limit:
            raise BudgetExceeded("Benchmark call/budget limit reached")
        self.calls += 1
        self.charged += self.reserve
        self.pending = True

    def settle(self, actual_usd=None, *, valid=False):
        if not self.pending:
            raise RuntimeError("No pending request")
        self.pending = False
        if actual_usd is None:
            self.unknown_cost_calls += 1
        else:
            actual = amount(actual_usd)
            self.known_actual += actual
            self.charged += max(Decimal(0), actual - self.reserve)
        self.valid_responses += int(valid)

    def report(self):
        return {"max_calls": self.max_calls, "budget_usd": str(self.limit),
                "reserve_usd_per_attempt": str(self.reserve), "attempts": self.calls,
                "conservative_reserved_or_actual_usd": str(self.charged),
                "known_actual_usd": str(self.known_actual), "unknown_cost_calls": self.unknown_cost_calls,
                "successful_valid_responses": self.valid_responses,
                "actual_cost_per_valid_response_usd": str(self.known_actual / self.valid_responses)
                    if self.valid_responses and not self.unknown_cost_calls else None,
                "reserved_cost_per_valid_response_usd": str(self.charged / self.valid_responses) if self.valid_responses else None,
                "account_spending_cap_enforced": False}
