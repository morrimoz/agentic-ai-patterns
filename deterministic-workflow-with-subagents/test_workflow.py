from patterns.workflow.demo import demo


def test_fixed_workflow_collects_specialist_evidence_and_pauses_before_effect():
    result = demo()
    assert result["status"] == "awaiting_approval"
    assert result["proposal"]["arguments"]["amount_cents"] == 12000
    assert result["steps"] == ["assemble", "plan", "investigate", "draft", "evaluate", "approval"]
    assert result["specialist_tool_calls"] >= 3
    assert result["effects_before_approval"] == 0
