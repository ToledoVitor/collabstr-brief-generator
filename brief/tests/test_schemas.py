"""Unit tests for request/response schemas (validation + normalization)."""

from django.test import SimpleTestCase
from pydantic import ValidationError

from brief.schemas import BriefRequest, BriefResult, Platform


class BriefRequestTests(SimpleTestCase):
    def test_valid_request_normalizes_brand(self):
        req = BriefRequest(
            brand="  Aera   Skincare ", platform="Instagram", goal="Awareness", tone="Friendly"
        )
        self.assertEqual(req.brand, "Aera Skincare")  # collapsed + trimmed
        self.assertEqual(req.platform, Platform.instagram)

    def test_off_allowlist_platform_rejected(self):
        with self.assertRaises(ValidationError):
            BriefRequest(brand="X Brand", platform="Facebook", goal="Awareness", tone="Friendly")

    def test_short_brand_rejected(self):
        with self.assertRaises(ValidationError):
            BriefRequest(brand="A", platform="Instagram", goal="Awareness", tone="Friendly")

    def test_bad_charset_rejected(self):
        with self.assertRaises(ValidationError):
            BriefRequest(
                brand="Brand<script>", platform="Instagram", goal="Awareness", tone="Friendly"
            )


class BriefResultTests(SimpleTestCase):
    def _data(self, angles=3, criteria=3):
        return {
            "brief": "ok",
            "angles": [{"title": f"t{i}", "description": f"d{i}"} for i in range(angles)],
            "criteria": [f"c{i}" for i in range(criteria)],
        }

    def test_valid_bounds(self):
        BriefResult.model_validate(self._data(3, 3))
        BriefResult.model_validate(self._data(4, 5))

    def test_too_few_angles_rejected(self):
        with self.assertRaises(ValidationError):
            BriefResult.model_validate(self._data(2, 3))

    def test_too_many_angles_rejected(self):
        with self.assertRaises(ValidationError):
            BriefResult.model_validate(self._data(5, 3))

    def test_criteria_bounds_enforced(self):
        with self.assertRaises(ValidationError):
            BriefResult.model_validate(self._data(3, 2))
        with self.assertRaises(ValidationError):
            BriefResult.model_validate(self._data(3, 6))

    def test_blank_criteria_stripped_then_revalidated(self):
        data = self._data(3, 3)
        data["criteria"] = ["ok", "  ", "also", " "]  # 4 raw -> 2 after strip -> fails min 3
        with self.assertRaises(ValidationError):
            BriefResult.model_validate(data)
