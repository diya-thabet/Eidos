"""Health rule modules organized by category (58 rules across 11 files)."""

# NOTE: Star imports are intentionally limited to the original 8 modules
# to avoid circular import issues. New modules (blame, dead_code,
# dependencies) are imported directly by code_health.py.
from app.analysis.health_rules.best_practices import *  # noqa: F401,F403
from app.analysis.health_rules.clean_code import *  # noqa: F401,F403
from app.analysis.health_rules.complexity import *  # noqa: F401,F403
from app.analysis.health_rules.design import *  # noqa: F401,F403
from app.analysis.health_rules.documentation import *  # noqa: F401,F403
from app.analysis.health_rules.naming import *  # noqa: F401,F403
from app.analysis.health_rules.security import *  # noqa: F401,F403
from app.analysis.health_rules.solid import *  # noqa: F401,F403
