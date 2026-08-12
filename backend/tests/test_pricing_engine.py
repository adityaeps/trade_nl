from decimal import Decimal

import pytest

from app.models.device import Device
from app.models.pricing import CompetitorPrice
from app.models.questionnaire import DeductionRule, DeductionType, DisqualifyStatus, Question
from app.services.pricing_engine import (
    calculate_quote_price,
    calculate_reference_price,
    filter_active_questions,
    filter_questions_for_device,
    find_disqualification,
)


def competitor_price(name: str, price: str) -> CompetitorPrice:
    return CompetitorPrice(
        device_id="00000000-0000-0000-0000-000000000001",
        competitor_name=name,
        price=Decimal(price),
        condition_tier="good",
        source_url="https://example.com",
    )


def test_calculate_reference_price_averages_multiple_competitors():
    prices = [competitor_price("swappie", "300.00"), competitor_price("buyback", "320.00")]
    assert calculate_reference_price(prices) == Decimal("310.00")


def test_calculate_reference_price_single_competitor_fallback():
    prices = [competitor_price("buyback", "250.00")]
    assert calculate_reference_price(prices) == Decimal("250.00")


def test_calculate_reference_price_empty_list_raises():
    with pytest.raises(ValueError):
        calculate_reference_price([])


def test_calculate_quote_price_stacks_multiple_deductions():
    rules = [
        DeductionRule(
            question_id=1, option_value="lightly_used",
            deduction_type=DeductionType.fixed, deduction_value=Decimal("15.00"),
        ),
        DeductionRule(
            question_id=2, option_value="no",
            deduction_type=DeductionType.fixed, deduction_value=Decimal("25.00"),
        ),
    ]
    answers = {"1": "lightly_used", "2": "no"}
    result = calculate_quote_price(Decimal("300.00"), answers, rules)
    assert result == Decimal("260.00")


def test_calculate_quote_price_applies_percentage_deduction():
    rules = [
        DeductionRule(
            question_id=1, option_value="heavily_used",
            deduction_type=DeductionType.percentage, deduction_value=Decimal("10.00"),
        ),
    ]
    answers = {"1": "heavily_used"}
    result = calculate_quote_price(Decimal("200.00"), answers, rules)
    assert result == Decimal("180.00")


def test_calculate_quote_price_floored_at_zero():
    rules = [
        DeductionRule(
            question_id=1, option_value="broken",
            deduction_type=DeductionType.fixed, deduction_value=Decimal("500.00"),
        ),
    ]
    answers = {"1": "broken"}
    result = calculate_quote_price(Decimal("100.00"), answers, rules)
    assert result == Decimal("0")


def test_calculate_quote_price_ignores_unmatched_and_disqualifying_rules():
    rules = [
        DeductionRule(
            question_id=1, option_value="yes",
            deduction_type=DeductionType.fixed, deduction_value=Decimal("0"),
        ),
        DeductionRule(
            question_id=2, option_value="yes",
            deduction_type=DeductionType.fixed, deduction_value=Decimal("999.00"),
            is_disqualifying=True, disqualify_status=DisqualifyStatus.rejected,
        ),
    ]
    answers = {"1": "yes", "2": "yes"}
    result = calculate_quote_price(Decimal("300.00"), answers, rules)
    assert result == Decimal("300.00")


def test_find_disqualification_sim_lock_rejected():
    rules = [
        DeductionRule(
            question_id=3, option_value="yes",
            deduction_type=DeductionType.fixed, deduction_value=Decimal("0"),
            is_disqualifying=True, disqualify_status=DisqualifyStatus.rejected,
        ),
    ]
    answers = {"3": "yes"}
    assert find_disqualification(answers, rules) == DisqualifyStatus.rejected


def test_find_disqualification_water_damage_manual_review():
    rules = [
        DeductionRule(
            question_id=4, option_value="yes",
            deduction_type=DeductionType.fixed, deduction_value=Decimal("0"),
            is_disqualifying=True, disqualify_status=DisqualifyStatus.manual_review,
        ),
    ]
    answers = {"4": "yes"}
    assert find_disqualification(answers, rules) == DisqualifyStatus.manual_review


def test_find_disqualification_powers_on_no_manual_review():
    rules = [
        DeductionRule(
            question_id=6, option_value="no",
            deduction_type=DeductionType.fixed, deduction_value=Decimal("0"),
            is_disqualifying=True, disqualify_status=DisqualifyStatus.manual_review,
        ),
    ]
    answers = {"6": "no"}
    assert find_disqualification(answers, rules) == DisqualifyStatus.manual_review


def test_find_disqualification_returns_none_when_nothing_matches():
    rules = [
        DeductionRule(
            question_id=3, option_value="yes",
            deduction_type=DeductionType.fixed, deduction_value=Decimal("0"),
            is_disqualifying=True, disqualify_status=DisqualifyStatus.rejected,
        ),
    ]
    answers = {"3": "no"}
    assert find_disqualification(answers, rules) is None


def test_filter_active_questions_skips_branch_when_parent_not_matched():
    overall_functional = Question(
        id=1, question_set_id=1, text="Is it working normally?",
        type="boolean", display_order=2, options=[],
    )
    face_id = Question(
        id=2, question_set_id=1, text="Does Face ID work?",
        type="boolean", display_order=5, options=[],
        depends_on_question_id=1, depends_on_value="no",
    )
    questions = [overall_functional, face_id]

    # Customer said "yes, everything works" - the branch question must not
    # appear at all, per §6.
    active = filter_active_questions(questions, {"1": "yes"})
    assert active == [overall_functional]

    # Customer said "no" - the branch question becomes active.
    active = filter_active_questions(questions, {"1": "no"})
    assert active == [overall_functional, face_id]


def test_filter_questions_for_device_gates_on_has_s_pen():
    s_pen_question = Question(
        id=15, question_set_id=2, text="Is the S-Pen present and working?",
        type="boolean", display_order=15, options=[],
        requires_device_attribute="has_s_pen",
    )
    plain_question = Question(
        id=1, question_set_id=2, text="Is the Samsung working properly?",
        type="boolean", display_order=2, options=[],
    )
    questions = [plain_question, s_pen_question]

    ultra = Device(
        brand="samsung", model="Galaxy S25 Ultra", storage_gb=256,
        category="phone", has_s_pen=True, slug="galaxy-s25-ultra",
    )
    a55 = Device(
        brand="samsung", model="Galaxy A55", storage_gb=128,
        category="phone", has_s_pen=False, slug="galaxy-a55",
    )

    assert filter_questions_for_device(questions, ultra) == questions
    assert filter_questions_for_device(questions, a55) == [plain_question]


# --- storage label parsing (scripts/sync_competitor_prices.py) -------------
# Storage labels are the join between our `devices.storage_gb` (always whole
# GB) and BuyBack.nl's per-model label text. A mismatch silently produces
# devices the price sync can't find - that's exactly how every 1TB device
# ended up unpriced, so the formats are pinned here.

import pytest as _pytest

from scripts.sync_competitor_prices import storage_gb_from_label


@_pytest.mark.parametrize(
    "label,expected",
    [
        ("64GB", 64),
        ("128GB", 128),
        ("512GB", 512),
        ("1TB", 1024),           # regression: was parsed as "1024GB" and never matched
        ("2TB", 2048),
        ("1 TB", 1024),          # spacing varies between models
        ("128GB/4GB", 128),      # "<storage>/<RAM>" - must take storage, not RAM
        ("256GB/12GB", 256),
        ("1TB/16GB", 1024),
        ("4G", None),            # some models ask connectivity before storage
        ("5G", None),
        ("Single-SIM", None),
        ("Dat weet ik niet", None),
        ("", None),
    ],
)
def test_storage_gb_from_label(label, expected):
    assert storage_gb_from_label(label) == expected
