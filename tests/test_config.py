from pathlib import Path

from realitydiff.config import Settings, project_root


def test_explicit_project_root_supports_installed_wheel_layout(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("REALITYDIFF_ROOT", str(tmp_path))
    assert project_root() == tmp_path.resolve()


def test_each_settings_instance_reads_the_current_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("REALITYDIFF_ROOT", str(tmp_path))
    monkeypatch.setenv("REALITYDIFF_ENV", "production")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    value = Settings()
    assert value.environment == "production"
    assert value.google_cloud_project == "test-project"
    assert value.fixture_path == tmp_path / "web" / "fixtures" / "demo.json"


def test_current_google_model_stack_is_the_default(monkeypatch) -> None:
    for name in (
        "REALITYDIFF_GEMINI_MODEL",
        "REALITYDIFF_TRIAGE_MODEL",
        "REALITYDIFF_EMBEDDING_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    value = Settings()
    assert value.gemini_model == "gemini-3.7-flash"
    assert value.triage_model == "gemini-3.5-flash-lite"
    assert value.embedding_model == "gemini-embedding-2"
