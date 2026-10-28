"""Runnable scenario using the implementation beside this file."""

from patterns.providers import emit


def demo():
    import tempfile
    from patterns.application.service import Service

    with tempfile.TemporaryDirectory() as path:
        service = Service(path)
        service.seed()
        case = service.submit("north", "INV-1042", "Investigate duplicate payment", request_id="route-demo")
        service.work("router-demo")
        state = service.case("north", case["case_id"])
        return {"executed": state["executed"], "proposal": state["proposal"], "plan": state["plan"]}


if __name__ == "__main__":
    emit(demo())
