"""Unit tests for the profanity guardrail."""

from django.test import SimpleTestCase

from brief.services.guardrails import contains_profanity


class GuardrailTests(SimpleTestCase):
    def test_clean_brands_pass(self):
        for brand in ["Aera Skincare", "Northpeak Coffee", "Lumen Audio", "Glow & Co."]:
            with self.subTest(brand=brand):
                self.assertFalse(contains_profanity(brand))

    def test_profanity_blocked(self):
        for text in ["shit happens", "this is fucking great", "bitch"]:
            with self.subTest(text=text):
                self.assertTrue(contains_profanity(text))

    def test_leet_substitutions_blocked(self):
        self.assertTrue(contains_profanity("sh1t"))  # 1 -> i
        self.assertTrue(contains_profanity("b1tch"))  # 1 -> i

    def test_spaced_evasion_blocked(self):
        self.assertTrue(contains_profanity("f u c k"))

    def test_no_false_positive_on_benign_substrings(self):
        # Scunthorpe-style guard: benign brands containing innocent substrings pass.
        for brand in ["Class Pass", "Assemble Studio", "Cockpit Gear"]:
            with self.subTest(brand=brand):
                self.assertFalse(contains_profanity(brand))
