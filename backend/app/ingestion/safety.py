"""Conservative safety gate, not a substitute for a production content classifier.

The two nuclear-system readings are quarantined in full until a separately reviewed
safe excerpt set exists. Pages discussing weapons in other readings are quarantined
as a unit, including their images, to avoid adjacent-text and citation leakage.
"""

import re

from app.ingestion.reading_models import SafetyLabel

QUARANTINED_COURSES = frozenset({"PHYS 230", "HIST 250"})
NUCLEAR_CONTEXT = re.compile(
    r"\b(bomb\w*|weapon\w*|plutonium|uranium|fissil\w*|fission\w*|"
    r"critical\s+mass|nuclear\s+(?:weapon\w*|bomb\w*|reactor\w*)|"
    r"neutron\w*|chain\s+reaction|reactor\w*)\b",
    re.IGNORECASE,
)


def classify_page(course_id: str, text: str) -> SafetyLabel:
    if course_id in QUARANTINED_COURSES or NUCLEAR_CONTEXT.search(text):
        return "restricted"
    return "safe"
