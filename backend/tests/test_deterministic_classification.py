import unittest

from app.models.enums import ComplaintCategory, Priority, Severity
from app.services.classification.base import ClassificationValidationError
from app.services.classification.deterministic import (
    DeterministicClassificationProvider,
)
from app.services.classification.service import ClassificationService


class DeterministicClassificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ClassificationService(
            provider=DeterministicClassificationProvider()
        )

    def classify(self, text: str, language: str | None = None):
        return self.service.classify(text=text, language=language)

    def test_pothole_extracts_location_and_high_severity_evidence(self) -> None:
        result = self.classify("Large pothole near the school gate.")

        self.assertEqual(result.category, ComplaintCategory.pothole)
        self.assertEqual(result.responsible_department, "Road Department")
        self.assertEqual(result.severity, Severity.high)
        self.assertEqual(result.priority, Priority.high)
        self.assertEqual(result.location_hint, "school gate")
        self.assertIn("pothole", result.matched_keywords)
        self.assertIn("school", result.severity_signals)
        self.assertFalse(result.needs_review)
        self.assertIsNone(result.confidence)
        self.assertEqual(result.provider, "deterministic_rules")

    def test_garbage_uses_time_impact_signal(self) -> None:
        result = self.classify("Garbage has not been collected for three days.")

        self.assertEqual(result.category, ComplaintCategory.garbage)
        self.assertEqual(result.responsible_department, "Sanitation Department")
        self.assertEqual(result.severity, Severity.high)
        self.assertIn("three days", result.severity_signals)
        self.assertFalse(result.needs_review)

    def test_water_leakage_uses_base_severity_without_invented_confidence(self) -> None:
        result = self.classify(
            "Water is leaking from a broken pipe outside the market."
        )

        self.assertEqual(result.category, ComplaintCategory.water_leakage)
        self.assertEqual(result.responsible_department, "Water Department")
        self.assertEqual(result.severity, Severity.medium)
        self.assertEqual(result.location_hint, "market")
        self.assertIsNone(result.confidence)

    def test_streetlight_location_is_extracted_before_time_phrase(self) -> None:
        result = self.classify("Streetlight is not working on MG Road at night.")

        self.assertEqual(result.category, ComplaintCategory.streetlight)
        self.assertEqual(result.responsible_department, "Electrical Department")
        self.assertEqual(result.location_hint, "MG Road")
        self.assertEqual(result.severity, Severity.high)

    def test_injury_escalates_traffic_accident_to_critical(self) -> None:
        result = self.classify(
            "Two people were injured in a traffic accident near the bus stand."
        )

        self.assertEqual(result.category, ComplaintCategory.traffic_accident)
        self.assertEqual(result.responsible_department, "Traffic Police")
        self.assertEqual(result.severity, Severity.critical)
        self.assertEqual(result.priority, Priority.critical)
        self.assertEqual(result.location_hint, "bus stand")
        self.assertIn("injured", result.severity_signals)

    def test_road_blockage_is_high_severity(self) -> None:
        result = self.classify("A fallen tree is blocking the main road.")

        self.assertEqual(result.category, ComplaintCategory.road_blockage)
        self.assertEqual(result.responsible_department, "Traffic Department")
        self.assertEqual(result.severity, Severity.high)

    def test_drainage_overflow_is_high_severity(self) -> None:
        result = self.classify(
            "Sewage is overflowing from an open drain near the hospital."
        )

        self.assertEqual(result.category, ComplaintCategory.drainage)
        self.assertEqual(result.responsible_department, "Drainage Department")
        self.assertEqual(result.severity, Severity.high)
        self.assertEqual(result.location_hint, "hospital")

    def test_unmatched_text_defaults_to_other_and_needs_review(self) -> None:
        result = self.classify("There is a problem.")

        self.assertEqual(result.category, ComplaintCategory.other)
        self.assertEqual(result.responsible_department, "General Administration")
        self.assertEqual(result.severity, Severity.low)
        self.assertEqual(result.matched_keywords, ())
        self.assertTrue(result.needs_review)
        self.assertIn("no complaint-category keyword", result.explanation)

    def test_ambiguous_keyword_tie_is_flagged_for_review(self) -> None:
        result = self.classify("pothole and garbage near the market")

        self.assertEqual(result.category, ComplaintCategory.pothole)
        self.assertTrue(result.needs_review)
        self.assertIn("Evidence tied with 'garbage'", result.explanation)

    def test_low_impact_terms_lower_base_severity(self) -> None:
        result = self.classify("There is a small pothole.")

        self.assertEqual(result.category, ComplaintCategory.pothole)
        self.assertEqual(result.severity, Severity.low)
        self.assertIn("small", result.severity_signals)

    def test_negated_injury_signal_does_not_escalate_severity(self) -> None:
        result = self.classify("There was a minor accident with no injuries.")

        self.assertEqual(result.category, ComplaintCategory.traffic_accident)
        self.assertEqual(result.severity, Severity.medium)
        self.assertNotIn("injuries", result.severity_signals)

    def test_language_alias_is_normalized(self) -> None:
        result = self.classify("pothole near the school", language="hi-IN")

        self.assertEqual(result.language, "hi")

    def test_indic_vowel_marks_are_preserved_for_keyword_matching(self) -> None:
        hindi = self.classify("सड़क पर बड़ा गड्ढा है", language="hi")
        gujarati = self.classify("રસ્તા પર ખાડો છે", language="gu")

        self.assertEqual(hindi.category, ComplaintCategory.pothole)
        self.assertEqual(hindi.severity, Severity.high)
        self.assertEqual(gujarati.category, ComplaintCategory.pothole)

    def test_blank_text_is_rejected(self) -> None:
        with self.assertRaises(ClassificationValidationError):
            self.classify("   ")

    def test_unsupported_language_is_rejected(self) -> None:
        with self.assertRaises(ClassificationValidationError):
            self.classify("pothole", language="xx")


if __name__ == "__main__":
    unittest.main()
