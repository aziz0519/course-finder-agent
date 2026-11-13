# Supplied samples

Authoritative MVP fixtures. Copy the supplied files here **without editing them**.

| File | Expected content |
|---|---|
| `course-catalog.json` | 14 courses, 1 programme, 5 requirement groups, `policies.max_units_per_term: 16`, `current_term: "Fall 2026"`, `next_term: "Spring 2027"` |
| `student-records.json` | 2 students: `student-001` (Sophomore) and `student-002` (Freshman) |
| `course-materials/*.pdf` | 5 catalogue-referenced readings (1 of 5 currently supplied) |

Structural expectations are encoded in `../schemas/`. Cross-record rules — unique IDs,
resolvable references, term consistency, completed/enrolled conflicts, the 16-unit
cap, the five requirement groups — are enforced by `scripts/validate_datasets.py`
rather than by the JSON Schema alone.

Do not add grades, seats, timetables, adviser profiles, or courses that are not in the
supplied catalogue. If a fact is missing, the application reports it as unavailable.
