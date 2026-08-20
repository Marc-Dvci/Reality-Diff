import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "web" / "fixtures" / "demo.json"
WORLD = json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_asset_ids_are_unique_and_every_image_is_bundled() -> None:
    assets = WORLD["assets"]
    asset_ids = [asset["id"] for asset in assets]
    assert len(asset_ids) == len(set(asset_ids))
    assert WORLD["meta"]["synthetic_media"] is True
    for asset in assets:
        relative = asset["image"].lstrip("/")
        path = (ROOT / "web" / relative).resolve()
        assert path.is_relative_to((ROOT / "web" / "assets").resolve())
        assert path.is_file(), asset["id"]


def test_subject_covers_and_change_evidence_reference_known_assets() -> None:
    assets_by_path = {asset["image"]: asset for asset in WORLD["assets"]}
    asset_ids = {asset["id"] for asset in WORLD["assets"]}
    subject_ids = [subject["id"] for subject in WORLD["subjects"]]
    assert len(subject_ids) == len(set(subject_ids))
    for subject in WORLD["subjects"]:
        assert subject["cover"] in assets_by_path
        for change in subject["changes"]:
            assert set(change["evidence"]).issubset(asset_ids), change["id"]


def test_contest_surface_has_nine_unique_use_cases() -> None:
    use_case_ids = [item["id"] for item in WORLD["use_cases"]]
    assert len(use_case_ids) == 9
    assert len(use_case_ids) == len(set(use_case_ids))


def test_lifestyle_gallery_is_diverse_bundled_and_licensed() -> None:
    gallery = WORLD["gallery"]
    assert len(gallery) >= 18
    assert len({item["category"] for item in gallery}) >= 8
    assert all(item["origin"].startswith("Pexels") for item in gallery)
    for item in gallery:
        path = ROOT / "web" / item["image"].lstrip("/")
        assert path.is_file(), item["id"]
