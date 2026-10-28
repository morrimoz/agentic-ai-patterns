"""Runnable scenario using the implementation beside this file."""

from patterns.providers import emit

from patterns.rag import run_evals


def demo():
    import tempfile

    with tempfile.TemporaryDirectory() as path:
        return run_evals(path)


if __name__ == "__main__":
    emit(demo())
