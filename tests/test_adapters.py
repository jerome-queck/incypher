import unittest

from agent_ext.adapters import ConfigurationError, LLMConfig, chat_completions_url


class AdapterTests(unittest.TestCase):
    def test_appends_chat_completions_path(self):
        self.assertEqual(
            chat_completions_url("https://model.example/v1/"),
            "https://model.example/v1/chat/completions",
        )

    def test_preserves_complete_chat_completions_path(self):
        url = "https://model.example/v1/chat/completions"
        self.assertEqual(chat_completions_url(url), url)

    def test_requires_all_runtime_values(self):
        with self.assertRaisesRegex(ConfigurationError, "LLM_MODEL"):
            LLMConfig.from_environment({
                "LLM_BASE_URL": "https://model.example/v1",
                "LLM_API_KEY": "synthetic",
            })

    def test_builds_runtime_config(self):
        config = LLMConfig.from_environment({
            "LLM_BASE_URL": "https://model.example/v1",
            "LLM_MODEL": "synthetic-model",
            "LLM_API_KEY": "synthetic-key",
        })
        self.assertEqual(config.model, "synthetic-model")
        self.assertEqual(config.chat_url, "https://model.example/v1/chat/completions")


if __name__ == "__main__":
    unittest.main()
