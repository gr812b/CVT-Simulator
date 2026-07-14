"""Baja track GPS analysis and CVT-simulator validation utilities."""

from .config import PipelineConfig
from .pipeline import AnalysisResult, run_analysis
from .signatures import SignatureResult, run_signature_analysis
from .workflow import FullWorkflowResult, run_full_workflow

__all__ = [
    "AnalysisResult",
    "PipelineConfig",
    "SignatureResult",
    "FullWorkflowResult",
    "run_analysis",
    "run_signature_analysis",
    "run_full_workflow",
]
__version__ = "0.2.0"
