import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import memory_store


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory_path = Path(self.temp_dir.name) / "memory.json"
        self.path_patch = patch.object(memory_store, "MEMORY_PATH", self.memory_path)
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_facts_round_trip(self):
        self.assertIn("Remembered: Likes tea", memory_store.remember_fact("Likes tea"))
        self.assertIn("Remembered: Uses dark mode", memory_store.remember_fact("Uses dark mode"))

        facts = memory_store.list_facts()
        self.assertIn("1. Likes tea", facts)
        self.assertIn("2. Uses dark mode", facts)

        self.assertIn("Forgot 1 fact(s)", memory_store.forget_fact("TEA"))
        self.assertNotIn("Likes tea", memory_store.list_facts())
        self.assertIn("Cleared 1 remembered fact(s)", memory_store.clear_all_facts())
        self.assertEqual(memory_store.list_facts(), "No facts remembered yet.")

    def test_fact_cap_drops_oldest_entry(self):
        for index in range(memory_store.MAX_FACTS + 1):
            memory_store.remember_fact(f"Fact {index}")

        facts = memory_store.list_facts()
        self.assertNotIn("Fact 0", facts)
        self.assertIn(f"Fact {memory_store.MAX_FACTS}", facts)
        self.assertEqual(facts.count("\n") + 1, memory_store.MAX_FACTS)

    def test_missing_or_corrupted_file_starts_empty(self):
        self.assertEqual(memory_store.list_facts(), "No facts remembered yet.")

        self.memory_path.write_text("{not valid json", encoding="utf-8")
        self.assertEqual(memory_store.list_facts(), "No facts remembered yet.")

        self.memory_path.write_text(json.dumps({"facts": [{"bad": "entry"}]}), encoding="utf-8")
        self.assertEqual(memory_store.list_facts(), "No facts remembered yet.")

    def test_macros_round_trip_and_overwrite(self):
        self.assertIn(
            "Saved macro 'morning'",
            memory_store.save_macro("morning", "Open the news and summarize it"),
        )
        self.assertEqual(
            memory_store.get_macro("morning"),
            "Open the news and summarize it",
        )
        self.assertIn("morning:", memory_store.list_macros())

        overwrite_message = memory_store.save_macro("morning", "Check the calendar")
        self.assertIn("Overwrote macro 'morning'", overwrite_message)
        self.assertEqual(memory_store.get_macro("morning"), "Check the calendar")

        self.assertIn("Deleted macro 'morning'", memory_store.delete_macro("morning"))
        self.assertIsNone(memory_store.get_macro("morning"))
        self.assertIn("No macro found", memory_store.delete_macro("morning"))


if __name__ == "__main__":
    unittest.main()
