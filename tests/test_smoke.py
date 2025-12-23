def test_imports_smoke():
    # Minimal smoke test: the CLI module should be importable.
    from src.main import app  # noqa: F401
