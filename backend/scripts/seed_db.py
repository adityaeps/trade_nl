"""Loads seed-data/devices.json and seed-data/questions.json into the database.

Run after `alembic upgrade head`:

    python scripts/seed_db.py

Idempotent - re-running against a database that's already seeded skips rows
that already exist (matched on devices.slug, question_sets.name, and
questions.(question_set_id, display_order)) rather than duplicating them.

Does NOT seed base_prices or competitor_prices: seed-data/devices.json
carries no pricing figures, and competitor prices are populated by the
Sprint 7 sync process (manual admin entry first, then
scripts/sync_competitor_prices.py) - see ARCHITECTURE.md §7. Devices exist
with no base_price row until that runs.
"""

import json
from pathlib import Path

from sqlmodel import Session, select

from app.db.session import engine
from app.models.device import Device
from app.models.questionnaire import DeductionRule, Question, QuestionSet

SEED_DIR = Path(__file__).resolve().parent.parent.parent / "seed-data"


def seed_devices(session: Session) -> None:
    data = json.loads((SEED_DIR / "devices.json").read_text())
    created = 0
    for entry in data["devices"]:
        existing = session.exec(select(Device).where(Device.slug == entry["slug"])).first()
        if existing:
            continue
        session.add(
            Device(
                brand=entry["brand"],
                model=entry["model"],
                storage_gb=entry["storage_gb"],
                color=entry.get("color"),
                category=entry["category"],
                has_s_pen=entry.get("has_s_pen", False),
                slug=entry["slug"],
            )
        )
        created += 1
    session.commit()
    print(f"devices: {created} created, {len(data['devices']) - created} already present")


def _get_or_create_question_set(session: Session, qs_def: dict) -> QuestionSet:
    existing = session.exec(
        select(QuestionSet).where(QuestionSet.name == qs_def["name"])
    ).first()
    if existing:
        return existing
    question_set = QuestionSet(
        category=qs_def["category"], brand=qs_def.get("brand"), name=qs_def["name"]
    )
    session.add(question_set)
    session.flush()  # assign question_set.id without committing yet
    return question_set


def _seed_question_list(
    session: Session, questions: list[dict], question_sets: dict[str, QuestionSet]
) -> int:
    """Seeds one brand's question list (iphone_questions or samsung_questions).

    Two passes: first insert every question so all local_ids resolve to a db
    id, then wire up depends_on_question_id - a question's depends_on parent
    is always defined earlier in the same list, but resolving in a second
    pass avoids relying on that ordering.
    """
    local_id_to_question: dict[str, Question] = {}
    pending_depends: list[tuple[Question, str, str]] = []
    flagged_count = 0

    for q_def in questions:
        question_set = question_sets[q_def["question_set"]]
        existing = session.exec(
            select(Question).where(
                Question.question_set_id == question_set.id,
                Question.display_order == q_def["display_order"],
            )
        ).first()
        if existing:
            local_id_to_question[q_def["local_id"]] = existing
            continue

        question = Question(
            question_set_id=question_set.id,
            text=q_def["text"],
            type=q_def["type"],
            display_order=q_def["display_order"],
            options=q_def["options"],
            requires_device_attribute=q_def.get("requires_device_attribute"),
        )
        session.add(question)
        session.flush()
        local_id_to_question[q_def["local_id"]] = question

        if "depends_on" in q_def:
            pending_depends.append(
                (question, q_def["depends_on"]["question"], q_def["depends_on"]["value"])
            )

        for rule_def in q_def.get("deduction_rules", []):
            session.add(
                DeductionRule(
                    question_id=question.id,
                    option_value=rule_def["option_value"],
                    deduction_type=rule_def["deduction_type"],
                    deduction_value=rule_def["deduction_value"],
                    is_disqualifying=rule_def.get("is_disqualifying", False),
                    disqualify_status=rule_def.get("disqualify_status"),
                )
            )
            # flag_for_business_review is informational content-authoring
            # metadata (source JSON's own note that the amount is an
            # unconfirmed placeholder) - not part of the deduction_rules
            # schema in ARCHITECTURE.md §5, so it isn't persisted. Counted
            # here just to surface it in the seeding summary below.
            if rule_def.get("flag_for_business_review"):
                flagged_count += 1

    for question, parent_local_id, value in pending_depends:
        parent = local_id_to_question[parent_local_id]
        question.depends_on_question_id = parent.id
        question.depends_on_value = value
        session.add(question)

    return flagged_count


def seed_questionnaires(session: Session) -> None:
    data = json.loads((SEED_DIR / "questions.json").read_text())

    question_sets = {
        qs_def["local_id"]: _get_or_create_question_set(session, qs_def)
        for qs_def in data["question_sets"]
    }
    session.commit()

    flagged_count = 0
    flagged_count += _seed_question_list(session, data["iphone_questions"], question_sets)
    flagged_count += _seed_question_list(session, data["samsung_questions"], question_sets)
    session.commit()

    print(
        f"questionnaires: {len(question_sets)} question sets seeded. "
        f"{flagged_count} deduction amounts are placeholders flagged for "
        "business review (see seed-data/questions.json open_questions)."
    )


def main() -> None:
    with Session(engine) as session:
        seed_devices(session)
        seed_questionnaires(session)


if __name__ == "__main__":
    main()
