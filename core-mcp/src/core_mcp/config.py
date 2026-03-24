from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    opa_url: str = "http://opa:8181"
    database_url: str = "postgresql://seed:seed@state-store:5432/seeddb"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
    templates_dir: str = "/app/templates"
    bootstrap_dir: str = "/app/bootstrap"
    seed_project_id: str = ""
    org_id: str = ""

    model_config = {"env_prefix": "CORE_MCP_"}
