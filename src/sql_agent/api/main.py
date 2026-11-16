"""Point d'entrée de l'API.

Lancer en local :  uvicorn sql_agent.api.main:app --reload
Documentation auto : http://localhost:8000/docs
"""

from fastapi import FastAPI

from sql_agent import __version__

app = FastAPI(
    title="SQL Agent",
    description="Repère, explique et corrige les requêtes SQL lentes – sans modifier la base.",
    version=__version__,
)


@app.get("/health")
def health() -> dict[str, str]:
    """Vérifie que l'API répond (utilisé par Docker et la CI)."""
    return {"status": "ok", "version": __version__}
