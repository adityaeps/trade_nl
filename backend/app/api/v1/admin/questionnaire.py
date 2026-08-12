from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.deps import get_current_admin
from app.db.session import get_session
from app.models.admin_user import AdminUser
from app.models.device import Brand, DeviceCategory
from app.models.questionnaire import (
    DeductionRule,
    DeductionType,
    DisqualifyStatus,
    Question,
    QuestionSet,
    QuestionType,
)

router = APIRouter(tags=["admin:questionnaire"])


# --- question sets ---------------------------------------------------------


class QuestionSetOut(BaseModel):
    id: int
    category: str
    brand: str | None
    name: str
    question_count: int


@router.get("/question-sets", response_model=list[QuestionSetOut])
def list_question_sets(
    session: Session = Depends(get_session), _: AdminUser = Depends(get_current_admin)
):
    sets = session.exec(select(QuestionSet).order_by(QuestionSet.id)).all()
    out = []
    for qs in sets:
        count = len(session.exec(select(Question).where(Question.question_set_id == qs.id)).all())
        out.append(
            QuestionSetOut(
                id=qs.id, category=qs.category, brand=qs.brand, name=qs.name, question_count=count
            )
        )
    return out


# --- deduction rules -------------------------------------------------------


class DeductionRuleIn(BaseModel):
    option_value: str
    deduction_type: DeductionType = DeductionType.fixed
    deduction_value: Decimal = Decimal("0")
    is_disqualifying: bool = False
    disqualify_status: DisqualifyStatus | None = None


class DeductionRuleOut(DeductionRuleIn):
    id: int
    question_id: int


# --- questions -------------------------------------------------------------


class QuestionOut(BaseModel):
    id: int
    question_set_id: int
    text: str
    type: str
    display_order: int
    options: list[dict[str, Any]]
    depends_on_question_id: int | None
    depends_on_value: str | None
    requires_device_attribute: str | None
    deduction_rules: list[DeductionRuleOut]


class QuestionIn(BaseModel):
    question_set_id: int
    text: str
    type: QuestionType = QuestionType.boolean
    display_order: int
    options: list[dict[str, Any]] = []
    depends_on_question_id: int | None = None
    depends_on_value: str | None = None
    requires_device_attribute: str | None = None


class QuestionUpdate(BaseModel):
    text: str | None = None
    type: QuestionType | None = None
    display_order: int | None = None
    options: list[dict[str, Any]] | None = None
    depends_on_question_id: int | None = None
    depends_on_value: str | None = None
    requires_device_attribute: str | None = None


def _question_out(session: Session, q: Question) -> QuestionOut:
    rules = session.exec(select(DeductionRule).where(DeductionRule.question_id == q.id)).all()
    return QuestionOut(
        id=q.id,
        question_set_id=q.question_set_id,
        text=q.text,
        type=q.type,
        display_order=q.display_order,
        options=q.options,
        depends_on_question_id=q.depends_on_question_id,
        depends_on_value=q.depends_on_value,
        requires_device_attribute=q.requires_device_attribute,
        deduction_rules=[DeductionRuleOut.model_validate(r, from_attributes=True) for r in rules],
    )


@router.get("/questions", response_model=list[QuestionOut])
def list_questions(
    question_set_id: int | None = None,
    session: Session = Depends(get_session),
    _: AdminUser = Depends(get_current_admin),
):
    query = select(Question)
    if question_set_id:
        query = query.where(Question.question_set_id == question_set_id)
    questions = session.exec(query.order_by(Question.question_set_id, Question.display_order)).all()
    return [_question_out(session, q) for q in questions]


@router.post("/questions", response_model=QuestionOut, status_code=201)
def create_question(
    payload: QuestionIn,
    session: Session = Depends(get_session),
    _: AdminUser = Depends(get_current_admin),
):
    if not session.get(QuestionSet, payload.question_set_id):
        raise HTTPException(status_code=404, detail="Question set not found")
    _validate_dependency(session, payload.depends_on_question_id, payload.depends_on_value, None)
    question = Question(**payload.model_dump())
    session.add(question)
    session.commit()
    session.refresh(question)
    return _question_out(session, question)


@router.put("/questions/{question_id}", response_model=QuestionOut)
def update_question(
    question_id: int,
    payload: QuestionUpdate,
    session: Session = Depends(get_session),
    _: AdminUser = Depends(get_current_admin),
):
    question = session.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    data = payload.model_dump(exclude_unset=True)
    _validate_dependency(
        session,
        data.get("depends_on_question_id", question.depends_on_question_id),
        data.get("depends_on_value", question.depends_on_value),
        question_id,
    )
    for field, value in data.items():
        setattr(question, field, value)
    session.add(question)
    session.commit()
    session.refresh(question)
    return _question_out(session, question)


@router.delete("/questions/{question_id}", status_code=204)
def delete_question(
    question_id: int,
    session: Session = Depends(get_session),
    _: AdminUser = Depends(get_current_admin),
):
    question = session.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    dependents = session.exec(
        select(Question).where(Question.depends_on_question_id == question_id)
    ).all()
    if dependents:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{len(dependents)} question(s) branch off this one "
                f"({', '.join(d.text[:40] for d in dependents)}). Repoint or delete those first."
            ),
        )

    for rule in session.exec(
        select(DeductionRule).where(DeductionRule.question_id == question_id)
    ).all():
        session.delete(rule)
    session.delete(question)
    session.commit()


def _validate_dependency(
    session: Session, parent_id: int | None, value: str | None, self_id: int | None
) -> None:
    """depends_on_question_id + depends_on_value must be set together, must
    reference a real question, and must not point at itself - a self- or
    dangling reference would make the question permanently invisible in the
    branching filter (ARCHITECTURE.md §6) with no obvious cause."""
    if parent_id is None and value is None:
        return
    if (parent_id is None) != (value is None):
        raise HTTPException(
            status_code=422,
            detail="depends_on_question_id and depends_on_value must be set together",
        )
    if self_id is not None and parent_id == self_id:
        raise HTTPException(status_code=422, detail="A question cannot depend on itself")
    parent = session.get(Question, parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="depends_on_question_id not found")
    if value not in [opt.get("value") for opt in parent.options]:
        raise HTTPException(
            status_code=422,
            detail=(
                f"depends_on_value '{value}' is not one of the parent question's options "
                f"({', '.join(str(o.get('value')) for o in parent.options)})"
            ),
        )


# --- deduction rule CRUD ---------------------------------------------------


@router.post("/questions/{question_id}/deduction-rules", response_model=DeductionRuleOut, status_code=201)
def create_deduction_rule(
    question_id: int,
    payload: DeductionRuleIn,
    session: Session = Depends(get_session),
    _: AdminUser = Depends(get_current_admin),
):
    question = session.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    _validate_rule(payload, question)
    rule = DeductionRule(question_id=question_id, **payload.model_dump())
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return DeductionRuleOut.model_validate(rule, from_attributes=True)


@router.put("/deduction-rules/{rule_id}", response_model=DeductionRuleOut)
def update_deduction_rule(
    rule_id: int,
    payload: DeductionRuleIn,
    session: Session = Depends(get_session),
    _: AdminUser = Depends(get_current_admin),
):
    rule = session.get(DeductionRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Deduction rule not found")
    _validate_rule(payload, session.get(Question, rule.question_id))
    for field, value in payload.model_dump().items():
        setattr(rule, field, value)
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return DeductionRuleOut.model_validate(rule, from_attributes=True)


@router.delete("/deduction-rules/{rule_id}", status_code=204)
def delete_deduction_rule(
    rule_id: int,
    session: Session = Depends(get_session),
    _: AdminUser = Depends(get_current_admin),
):
    rule = session.get(DeductionRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Deduction rule not found")
    session.delete(rule)
    session.commit()


def _validate_rule(payload: DeductionRuleIn, question: Question | None) -> None:
    if payload.is_disqualifying and payload.disqualify_status is None:
        raise HTTPException(
            status_code=422,
            detail="disqualify_status is required when is_disqualifying is true (§6)",
        )
    if not payload.is_disqualifying and payload.disqualify_status is not None:
        raise HTTPException(
            status_code=422,
            detail="disqualify_status may only be set when is_disqualifying is true",
        )
    if payload.deduction_value < 0:
        raise HTTPException(status_code=422, detail="deduction_value cannot be negative")
    if question and question.options:
        valid = [opt.get("value") for opt in question.options]
        if payload.option_value not in valid:
            raise HTTPException(
                status_code=422,
                detail=f"option_value must be one of the question's options ({', '.join(map(str, valid))})",
            )
