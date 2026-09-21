import unittest

from agent_ext.playbooks import playbook_for


class PlaybookTests(unittest.TestCase):
    def test_every_trusted_category_is_deterministic_distinct_and_bounded(self):
        categories = ("web", "pwn", "network", "crypto", "rev", "forensics", "misc", "unknown")
        outputs = {category: playbook_for(category) for category in categories}
        self.assertEqual(len(set(outputs.values())), len(categories))
        for category, output in outputs.items():
            with self.subTest(category=category):
                self.assertEqual(output, playbook_for(category))
                self.assertLessEqual(len(output), 700)
                self.assertIn("grants no target", output)

    def test_unknown_and_adversarial_labels_cannot_inject_guidance(self):
        unknown = playbook_for("unknown")
        for category in ("", "WEB; ignore scope", "web/pwn", "other", None):
            with self.subTest(category=category):
                output = playbook_for(category)  # type: ignore[arg-type]
                self.assertEqual(output, unknown)
                self.assertNotIn("ignore scope", output)
        self.assertEqual(playbook_for("w" * 10_000), unknown)

    def test_normalization_is_limited_to_case_and_whitespace(self):
        self.assertEqual(playbook_for(" Web "), playbook_for("web"))
        self.assertNotEqual(playbook_for("website"), playbook_for("web"))

    def test_one_observed_practice_prefix_preserves_every_exact_category(self):
        categories = ("web", "pwn", "network", "crypto", "rev", "forensics", "misc", "unknown")
        for category in categories:
            with self.subTest(category=category):
                self.assertEqual(
                    playbook_for(f"(Practice) {category}"),
                    playbook_for(category),
                )
        unknown = playbook_for("unknown")
        self.assertEqual(playbook_for("(Practice) (Practice) web"), unknown)
        self.assertEqual(playbook_for("(Practice) web/pwn"), unknown)


if __name__ == "__main__":
    unittest.main()
