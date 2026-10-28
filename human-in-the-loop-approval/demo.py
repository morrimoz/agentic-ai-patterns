"""Runnable scenario using the implementation beside this file."""

from patterns.providers import emit


def demo():
    import tempfile
    from patterns.application.service import Service

    with tempfile.TemporaryDirectory() as path:
        service = Service(path)
        service.seed()
        case = service.submit("north", "INV-1042", "Investigate", request_id="approval-demo")
        service.work("first-process")
        before = service.case("north", case["case_id"])
        effects = len(service.erp.credits("north", "INV-1042"))
        reopened = Service(path)
        reopened.resolve(
            "north",
            case["case_id"],
            action="edit",
            actor="operator",
            expected_version=before["approval"]["version"],
            amount_cents=10000,
        )
        reopened.work("restarted-process")
        return {
            "paused": before["status"],
            "effects_before_approval": effects,
            "result": reopened.case("north", case["case_id"]),
        }


if __name__ == "__main__":
    emit(demo())
