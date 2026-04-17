"""
Document templates.

Each template defines the sections and structure for a document type.
Templates are pure data; generation logic lives in ``generator.py``.
"""

from __future__ import annotations

from app.docgen.models import DocType

# Section key constants used by generator to fill in content
SEC_OVERVIEW = "overview"
SEC_TECH_STACK = "tech_stack"
SEC_MODULES = "modules"
SEC_ENTRY_POINTS = "entry_points"
SEC_KEY_FLOWS = "key_flows"
SEC_DEPENDENCIES = "dependencies"
SEC_METRICS = "metrics"
SEC_FILES = "files"
SEC_CLASSES = "classes"
SEC_PUBLIC_API = "public_api"
SEC_INTERNAL = "internal"
SEC_FLOW_STEPS = "flow_steps"
SEC_CALLERS = "callers"
SEC_SIDE_EFFECTS = "side_effects"
SEC_QUICK_START = "quick_start"
SEC_CONFIGURATION = "configuration"
SEC_KNOWN_RISKS = "known_risks"
SEC_HOTSPOTS = "hotspots"


TEMPLATE_SECTIONS: dict[DocType, list[tuple[str, str]]] = {
    DocType.README: [
        (SEC_OVERVIEW, "Overview"),
        (SEC_TECH_STACK, "Tech Stack"),
        (SEC_MODULES, "Modules"),
        (SEC_ENTRY_POINTS, "Entry Points"),
        (SEC_KEY_FLOWS, "Key Flows"),
        (SEC_METRICS, "Metrics"),
    ],
    DocType.ARCHITECTURE: [
        (SEC_OVERVIEW, "Architecture Overview"),
        (SEC_MODULES, "Module Map"),
        (SEC_DEPENDENCIES, "Module Dependencies"),
        (SEC_ENTRY_POINTS, "Entry Points"),
        (SEC_KEY_FLOWS, "Key Flows"),
        (SEC_METRICS, "Code Metrics"),
        (SEC_HOTSPOTS, "Hotspots"),
    ],
    DocType.MODULE: [
        (SEC_OVERVIEW, "Overview"),
        (SEC_FILES, "Files"),
        (SEC_CLASSES, "Classes & Interfaces"),
        (SEC_PUBLIC_API, "Public API"),
        (SEC_INTERNAL, "Internal Details"),
        (SEC_DEPENDENCIES, "Dependencies"),
    ],
    DocType.FLOW: [
        (SEC_OVERVIEW, "Overview"),
        (SEC_FLOW_STEPS, "Execution Steps"),
        (SEC_CALLERS, "Entry Points / Callers"),
        (SEC_SIDE_EFFECTS, "Side Effects"),
    ],
    DocType.RUNBOOK: [
        (SEC_OVERVIEW, "Overview"),
        (SEC_QUICK_START, "Quick Start"),
        (SEC_ENTRY_POINTS, "Entry Points"),
        (SEC_CONFIGURATION, "Configuration"),
        (SEC_KNOWN_RISKS, "Known Risks & Hotspots"),
    ],
}


def get_template_sections(doc_type: DocType) -> list[tuple[str, str]]:
    """Return (section_key, heading) pairs for a document type."""
    return TEMPLATE_SECTIONS.get(doc_type, [])
