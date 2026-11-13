# Course materials

The catalogue references five PDFs. Copy them here using exactly these filenames.

| Course | Reading | Filename | Status |
|---|---|---|---|
| PHYS 230 | Critical mass | `phys230-critical-mass.pdf` | ✅ present — `sha256` `9cc30f28…`, 11 pages, preflight complete |
| PHYS 350 | Bohr model | `phys350-bohr-model.pdf` | ✅ present — 12 pages |
| ENGL 120 | The Raven | `engl120-the-raven.pdf` | ✅ present — 15 pages |
| HIST 210 | Niels Bohr | `hist210-niels-bohr.pdf` | ✅ present — 17 pages |
| HIST 250 | Demon core | `hist250-demon-core.pdf` | ✅ present — 9 pages |

Notes:

- PDF bytes are gitignored. Presence, checksum, and page count are tracked in
  `data/manifests/course_readings_manifest.json`. Update that manifest when you add a file.
- Do not rename files: the catalogue `materials[].file` values and the manifest both
  expect these exact names.
- The PHYS 230 file is expected to be born-digital with a usable text layer. Do not
  assume the other four share its layout; each gets its own preflight in M2.
- Retain the source attribution and licence notice (the PHYS 230 PDF carries a
  Creative Commons Attribution-ShareAlike statement on its final page).
