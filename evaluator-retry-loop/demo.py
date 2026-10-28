"""Runnable scenario using the implementation beside this file."""

from patterns.providers import emit


def demo():
    import tempfile
    from patterns.application.service import Service
    from patterns.providers import FixtureModel

    with tempfile.TemporaryDirectory() as path:
        service = Service(path, model=FixtureModel(fault="bad_first_draft"))
        service.seed()
        case = service.submit("north", "INV-1042", "Investigate duplicate payment", request_id="repair-demo")
        service.work("evaluator-demo")
        return {
            "case": service.case("north", case["case_id"]),
            "evaluation_events": [
                e for e in service.events("north", case["case_id"]) if e["kind"].startswith("evaluation.")
            ],
        }


if __name__ == "__main__":
    emit(demo())
