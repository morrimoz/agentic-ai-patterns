"""Runnable scenario using the implementation beside this file."""

from patterns.providers import emit


def demo():
    import tempfile
    from patterns.application.service import Service

    with tempfile.TemporaryDirectory() as path:
        service = Service(path)
        service.seed()
        case = service.submit("north", "INV-1042", "Investigate", request_id="recovery-demo")
        service.work("first")
        pending = service.case("north", case["case_id"])
        service.resolve(
            "north",
            case["case_id"],
            action="approve",
            actor="operator",
            expected_version=pending["approval"]["version"],
        )
        service.work("first", fault="after_effect")
        after_crash = len(service.erp.credits("north", "INV-1042"))
        Service(path).work("second", now=service.clock() + 10)
        return {
            "effects_after_crash": after_crash,
            "effects_after_retry": len(service.erp.credits("north", "INV-1042")),
            "result": service.case("north", case["case_id"]),
            "work_document": service.docs.get("north", case["case_id"]),
        }


if __name__ == "__main__":
    emit(demo())
