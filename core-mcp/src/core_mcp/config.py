from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    opa_url: str = "http://opa:8181"
    database_url: str = "postgresql://seed:seed@state-store:5432/seeddb"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
    templates_dir: str = "/app/templates"
    bootstrap_dir: str = "/app/bootstrap"
    bootstrap_projects_dir: str = "/app/bootstrap/projects"
    seed_project_id: str = ""
    seed_project_number: str = ""
    org_id: str = ""
    github_owner: str = ""

    model_config = {"env_prefix": "CORE_MCP_"}
