"""Integration tests for /admin/question-sets, /admin/questions, /admin/deduction-rules."""

from tests.factories import make_deduction_rule, make_question, make_question_set


def test_list_question_sets_with_counts(admin_client, db_session):
    qs = make_question_set(db_session)
    make_question(db_session, qs, display_order=1)
    make_question(db_session, qs, display_order=2)
    db_session.commit()

    resp = admin_client.get("/api/v1/admin/question-sets")
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["id"] == qs.id)
    assert row["question_count"] == 2


def test_list_questions_filtered_by_set(admin_client, db_session):
    qs_a = make_question_set(db_session)
    qs_b = make_question_set(db_session)
    q_a = make_question(db_session, qs_a)
    make_question(db_session, qs_b)
    db_session.commit()

    resp = admin_client.get("/api/v1/admin/questions", params={"question_set_id": qs_a.id})
    assert resp.status_code == 200
    ids = {q["id"] for q in resp.json()}
    assert ids == {q_a.id}


def test_create_question_requires_valid_question_set(admin_client):
    resp = admin_client.post(
        "/api/v1/admin/questions",
        json={"question_set_id": 999999, "text": "x", "type": "boolean", "display_order": 1},
    )
    assert resp.status_code == 404


def test_create_question_with_valid_dependency(admin_client, db_session):
    qs = make_question_set(db_session)
    parent = make_question(
        db_session, qs, display_order=1, options=[{"label": "No", "value": "no"}]
    )
    db_session.commit()

    resp = admin_client.post(
        "/api/v1/admin/questions",
        json={
            "question_set_id": qs.id,
            "text": "child",
            "type": "boolean",
            "display_order": 2,
            "depends_on_question_id": parent.id,
            "depends_on_value": "no",
        },
    )
    assert resp.status_code == 201, resp.text


def test_create_question_dependency_value_not_in_parent_options_422(admin_client, db_session):
    qs = make_question_set(db_session)
    parent = make_question(db_session, qs, options=[{"label": "No", "value": "no"}])
    db_session.commit()

    resp = admin_client.post(
        "/api/v1/admin/questions",
        json={
            "question_set_id": qs.id,
            "text": "child",
            "type": "boolean",
            "display_order": 2,
            "depends_on_question_id": parent.id,
            "depends_on_value": "not-a-real-option",
        },
    )
    assert resp.status_code == 422


def test_create_question_dependency_only_one_field_set_422(admin_client, db_session):
    qs = make_question_set(db_session)
    db_session.commit()

    resp = admin_client.post(
        "/api/v1/admin/questions",
        json={
            "question_set_id": qs.id,
            "text": "child",
            "type": "boolean",
            "display_order": 2,
            "depends_on_value": "no",
        },
    )
    assert resp.status_code == 422


def test_update_question_cannot_depend_on_itself_422(admin_client, db_session):
    qs = make_question_set(db_session)
    q = make_question(db_session, qs, options=[{"label": "No", "value": "no"}])
    db_session.commit()

    resp = admin_client.put(
        f"/api/v1/admin/questions/{q.id}",
        json={"depends_on_question_id": q.id, "depends_on_value": "no"},
    )
    assert resp.status_code == 422


def test_update_question_text(admin_client, db_session):
    qs = make_question_set(db_session)
    q = make_question(db_session, qs, text="old text")
    db_session.commit()

    resp = admin_client.put(f"/api/v1/admin/questions/{q.id}", json={"text": "new text"})
    assert resp.status_code == 200
    assert resp.json()["text"] == "new text"


def test_delete_question_blocked_by_dependents_409(admin_client, db_session):
    qs = make_question_set(db_session)
    parent = make_question(db_session, qs, options=[{"label": "No", "value": "no"}])
    make_question(
        db_session, qs, depends_on_question_id=parent.id, depends_on_value="no", display_order=2
    )
    db_session.commit()

    resp = admin_client.delete(f"/api/v1/admin/questions/{parent.id}")
    assert resp.status_code == 409


def test_delete_question_without_dependents(admin_client, db_session):
    qs = make_question_set(db_session)
    q = make_question(db_session, qs)
    db_session.commit()

    resp = admin_client.delete(f"/api/v1/admin/questions/{q.id}")
    assert resp.status_code == 204


def test_create_deduction_rule_disqualifying_requires_status_422(admin_client, db_session):
    qs = make_question_set(db_session)
    q = make_question(db_session, qs, options=[{"label": "Yes", "value": "yes"}])
    db_session.commit()

    resp = admin_client.post(
        f"/api/v1/admin/questions/{q.id}/deduction-rules",
        json={"option_value": "yes", "is_disqualifying": True},
    )
    assert resp.status_code == 422


def test_create_deduction_rule_negative_value_422(admin_client, db_session):
    qs = make_question_set(db_session)
    q = make_question(db_session, qs, options=[{"label": "Yes", "value": "yes"}])
    db_session.commit()

    resp = admin_client.post(
        f"/api/v1/admin/questions/{q.id}/deduction-rules",
        json={"option_value": "yes", "deduction_value": "-5.00"},
    )
    assert resp.status_code == 422


def test_create_deduction_rule_option_not_in_question_options_422(admin_client, db_session):
    qs = make_question_set(db_session)
    q = make_question(db_session, qs, options=[{"label": "Yes", "value": "yes"}])
    db_session.commit()

    resp = admin_client.post(
        f"/api/v1/admin/questions/{q.id}/deduction-rules",
        json={"option_value": "not-an-option", "deduction_value": "5.00"},
    )
    assert resp.status_code == 422


def test_create_and_update_deduction_rule(admin_client, db_session):
    qs = make_question_set(db_session)
    q = make_question(db_session, qs, options=[{"label": "Yes", "value": "yes"}])
    db_session.commit()

    created = admin_client.post(
        f"/api/v1/admin/questions/{q.id}/deduction-rules",
        json={"option_value": "yes", "deduction_type": "fixed", "deduction_value": "10.00"},
    )
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]

    updated = admin_client.put(
        f"/api/v1/admin/deduction-rules/{rule_id}",
        json={"option_value": "yes", "deduction_type": "fixed", "deduction_value": "20.00"},
    )
    assert updated.status_code == 200
    assert updated.json()["deduction_value"] == "20.00"


def test_delete_deduction_rule(admin_client, db_session):
    qs = make_question_set(db_session)
    q = make_question(db_session, qs, options=[{"label": "Yes", "value": "yes"}])
    rule = make_deduction_rule(db_session, q, "yes")
    db_session.commit()

    resp = admin_client.delete(f"/api/v1/admin/deduction-rules/{rule.id}")
    assert resp.status_code == 204
