"""Runnable scenario using the implementation beside this file."""

from patterns.providers import emit


def demo():
    import tempfile
    from patterns.application.service import Service
    from patterns.workflow.specialists import investigate

    with tempfile.TemporaryDirectory() as path:
        service = Service(path)
        service.seed()
        return investigate(service, "north", "demo", "INV-1042", coordinator=True)


if __name__ == "__main__":
    emit(demo())
