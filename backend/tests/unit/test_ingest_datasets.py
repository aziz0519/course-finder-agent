"""Review-manifest selection at the operator CLI boundary."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import ingest_datasets as cli


@pytest.mark.parametrize("directory", [False, True])
def test_explicit_nonfile_review_path_is_rejected_before_ingestion(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    directory: bool,
) -> None:
    review_path = tmp_path / "reviews.json"
    if directory:
        review_path.mkdir()

    def unexpected_load(*args, **kwargs):
        pytest.fail("invalid explicit --reviews path reached dataset loading")

    monkeypatch.setattr(cli, "load_dataset", unexpected_load)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--reviews", str(review_path)])
    assert exc.value.code == 2
    assert "--reviews must point to an existing review manifest file" in capsys.readouterr().err


@pytest.mark.parametrize("explicit", [False, True])
def test_missing_default_review_is_optional_and_explicit_existing_manifest_is_loaded(
    synthetic,
    monkeypatch: pytest.MonkeyPatch,
    explicit: bool,
) -> None:
    root, document, _, repository = synthetic
    materials = root / "samples" / "course-materials"
    materials.mkdir(parents=True)
    (materials / document.source_filename).write_bytes(
        (root / document.source_filename).read_bytes()
    )
    monkeypatch.setattr(
        cli,
        "load_dataset",
        lambda _: SimpleNamespace(catalog=SimpleNamespace(reading_documents=(document,))),
    )
    args = ["--data-root", str(root), "--output", str(repository.root)]
    review_paths = []
    load_reviews = cli.load_reviews

    def track_reviews(path):
        review_paths.append(path)
        return load_reviews(path)

    monkeypatch.setattr(cli, "load_reviews", track_reviews)
    if explicit:
        manifest = root / "custom-reviews.json"
        manifest.write_text('{"documents": {}}', encoding="utf-8")
        args.extend(["--reviews", str(manifest)])
    assert cli.main(args) == 0
    assert review_paths == ([root / "custom-reviews.json"] if explicit else [])
    assert len(repository.inventory()) == 1
    assert not repository.inventory()[0]["active"]
