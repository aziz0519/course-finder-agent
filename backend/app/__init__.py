"""Student learning and course-planning assistant (MVP).

Package layout mirrors the boundaries in AGENTS.md section 12. Imports must flow
inward: ``api`` -> ``services`` -> ``domain``/``repositories``. Domain code must not
import FastAPI, an agent runtime, or a model-provider SDK.
"""

__version__ = "0.1.0"
