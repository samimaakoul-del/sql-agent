"""Configuration lue depuis les variables d'environnement (ou le fichier .env)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Connexion PostgreSQL en LECTURE SEULE (garde-fou F6)
    database_url: str = "postgresql://agent_ro:agent_ro@localhost:5432/shop"

    # Ollama (LLM local)
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b"

    # Nombre de requêtes lentes renvoyées par défaut (F1)
    top_n: int = 10


settings = Settings()
