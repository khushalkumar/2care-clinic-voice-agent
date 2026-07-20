from pathlib import Path

WORKFLOW = Path(__file__).parents[2] / ".github" / "workflows" / "deploy-staging.yml"


def test_staging_deployment_runs_and_waits_for_database_migrations() -> None:
    workflow = WORKFLOW.read_text()

    migration_marker = "      - name: Run database migrations"
    retell_marker = "      - name: Configure Retell staging agent"

    assert migration_marker in workflow
    assert "aws ecs run-task" in workflow
    assert '"command":["alembic","upgrade","head"]' in workflow
    assert "aws ecs wait tasks-stopped" in workflow
    assert "MIGRATION_EXIT_CODE" in workflow
    assert workflow.index(migration_marker) < workflow.index(retell_marker)
