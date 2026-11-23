"""F2 - Analyseur : lecture des plans EXPLAIN et détection des problèmes par règles.

Responsable : Ahmed Sami.
"""

from sql_agent.analyzer.explain import AnalysisError, analyze
from sql_agent.analyzer.models import Diagnosis, Finding, IndexCandidate

__all__ = ["AnalysisError", "Diagnosis", "Finding", "IndexCandidate", "analyze"]
