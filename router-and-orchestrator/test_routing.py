import pytest
from patterns.routing import Plan, Step, validate_plan
from patterns.routing.demo import demo


def test_plan_preserves_stable_job_ids_and_dependency_order():
    plan = Plan(
        steps=[
            Step(id="a", capability="ledger", depends_on=[]),
            Step(id="b", capability="policy", depends_on=[]),
            Step(id="c", capability="draft", depends_on=["a", "b"]),
        ]
    )
    assert [step.id for step in validate_plan(plan).steps] == ["a", "b", "c"]
    result = demo()
    assert result["executed"] == ["ledger", "policy", "draft"]
    assert result["proposal"]["arguments"]["amount_cents"] == 12000


@pytest.mark.parametrize(
    "steps",
    [
        [{"id": "a", "capability": "unknown", "depends_on": []}],
        [{"id": "a", "capability": "ledger", "depends_on": ["missing"]}],
        [
            {"id": "a", "capability": "ledger", "depends_on": []},
            {"id": "a", "capability": "policy", "depends_on": []},
        ],
        [{"id": "c", "capability": "draft", "depends_on": []}],
    ],
)
def test_invalid_plans_cannot_execute(steps):
    with pytest.raises(ValueError):
        validate_plan(Plan(steps=[Step(**row) for row in steps]))
