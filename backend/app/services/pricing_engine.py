"""Pure pricing/questionnaire logic - see ARCHITECTURE.md §6.

No DB or HTTP calls in this module (§6, CLAUDE.md). Callers (the API layer)
are responsible for fetching devices/prices/questions/rules and persisting
results. `answers` throughout is keyed by question id as a string, matching
the shape of `quotes.answers` jsonb once round-tripped through JSON.
"""

from decimal import Decimal

from app.models.device import Device
from app.models.pricing import CompetitorPrice
from app.models.questionnaire import DeductionRule, DeductionType, DisqualifyStatus, Question


def calculate_reference_price(competitor_prices: list[CompetitorPrice]) -> Decimal:
    """Average of available competitor prices. Falls back to the single
    available price if only one competitor lists the device."""
    if not competitor_prices:
        raise ValueError("calculate_reference_price requires at least one competitor price")
    prices = [cp.price for cp in competitor_prices]
    return sum(prices, Decimal(0)) / Decimal(len(prices))


def filter_questions_for_device(questions: list[Question], device: Device) -> list[Question]:
    """Device-attribute gating (§6): a question with requires_device_attribute
    set (e.g. "has_s_pen") only applies to devices where that boolean
    attribute is true. Questions with no requirement always pass through."""
    return [
        q
        for q in questions
        if q.requires_device_attribute is None or getattr(device, q.requires_device_attribute, False)
    ]


def filter_active_questions(questions: list[Question], answers: dict[str, str]) -> list[Question]:
    """Branching resolution (§6): a question with depends_on_question_id set
    is only active if its parent question was answered with depends_on_value.
    Questions with no dependency always pass through."""
    return [
        q
        for q in questions
        if q.depends_on_question_id is None
        or answers.get(str(q.depends_on_question_id)) == q.depends_on_value
    ]


def find_disqualification(
    answers: dict[str, str], deduction_rules: list[DeductionRule]
) -> DisqualifyStatus | None:
    """Checks the answer set against disqualifying rules before any normal
    deduction math runs (§6). Returns the status to short-circuit pricing
    with, or None if nothing disqualifies. If answers somehow match both
    kinds, `rejected` wins as the more severe outcome."""
    statuses = {
        rule.disqualify_status
        for rule in deduction_rules
        if rule.is_disqualifying and answers.get(str(rule.question_id)) == rule.option_value
    }
    if DisqualifyStatus.rejected in statuses:
        return DisqualifyStatus.rejected
    if DisqualifyStatus.manual_review in statuses:
        return DisqualifyStatus.manual_review
    return None


def calculate_quote_price(
    base_price: Decimal,
    answers: dict[str, str],
    deduction_rules: list[DeductionRule],
) -> Decimal:
    """Applies each matching deduction rule to base_price and returns the
    final price, floored at 0. Callers must run find_disqualification first
    and skip this entirely if it returns a status (§6) - disqualifying rules
    are ignored here regardless, since their deduction_value is meaningless."""
    price = base_price
    for rule in deduction_rules:
        if rule.is_disqualifying or answers.get(str(rule.question_id)) != rule.option_value:
            continue
        if rule.deduction_type == DeductionType.percentage:
            price -= base_price * (rule.deduction_value / Decimal(100))
        else:
            price -= rule.deduction_value
    return max(price, Decimal(0))
