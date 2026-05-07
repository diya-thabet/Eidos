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

# New section keys for enhanced doc types
SEC_CLASSES_DETAIL = "classes_detail"
SEC_METHODS = "methods"
SEC_PARAMETERS = "parameters"
SEC_SETUP = "setup"
SEC_PROJECT_STRUCTURE = "project_structure"
SEC_WHERE_TO_FIND = "where_to_find"
SEC_FIRST_STEPS = "first_steps"
SEC_ADDED = "added"
SEC_REMOVED = "removed"
SEC_MODIFIED = "modified"
SEC_BREAKING_CHANGES = "breaking_changes"
SEC_EXTERNAL_DEPS = "external_deps"
SEC_INTERNAL_DEPS = "internal_deps"
SEC_CIRCULAR_DEPS = "circular_deps"


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
    DocType.API_REFERENCE: [
        (SEC_OVERVIEW, "API Reference Overview"),
        (SEC_CLASSES_DETAIL, "Classes & Types"),
        (SEC_METHODS, "Public Methods"),
        (SEC_PARAMETERS, "Parameters & Return Types"),
    ],
    DocType.ONBOARDING: [
        (SEC_OVERVIEW, "Welcome"),
        (SEC_SETUP, "Setup & Installation"),
        (SEC_PROJECT_STRUCTURE, "Project Structure"),
        (SEC_ENTRY_POINTS, "Entry Points"),
        (SEC_KEY_FLOWS, "Key Flows"),
        (SEC_WHERE_TO_FIND, "Where to Find Things"),
        (SEC_FIRST_STEPS, "First Steps for Contributors"),
    ],
    DocType.CHANGELOG: [
        (SEC_OVERVIEW, "Change Summary"),
        (SEC_ADDED, "Added"),
        (SEC_REMOVED, "Removed"),
        (SEC_MODIFIED, "Modified"),
        (SEC_BREAKING_CHANGES, "Breaking Changes"),
    ],
    DocType.DEPENDENCY_MAP: [
        (SEC_OVERVIEW, "Dependency Overview"),
        (SEC_EXTERNAL_DEPS, "External Dependencies"),
        (SEC_INTERNAL_DEPS, "Internal Module Dependencies"),
        (SEC_CIRCULAR_DEPS, "Circular Dependencies"),
        (SEC_METRICS, "Dependency Metrics"),
    ],
}


def get_template_sections(doc_type: DocType) -> list[tuple[str, str]]:
    """Return (section_key, heading) pairs for a document type."""
    return TEMPLATE_SECTIONS.get(doc_type, [])
