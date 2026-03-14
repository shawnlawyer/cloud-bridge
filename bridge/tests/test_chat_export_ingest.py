import tempfile
import unittest

from bridge.ingest.chat_export import ingest_chat_export, load_chat_export
from bridge.workers import FileTaskStore


class TestChatExportIngest(unittest.TestCase):
    def test_load_chat_export_supports_mapping_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sample_path = f"{temp_dir}/mapping.json"
            with open(sample_path, "w", encoding="utf-8") as handle:
                handle.write(
                    '{"conversations":[{"id":"conv-1","title":"Mapped","mapping":{"b":{"message":{"author":{"role":"assistant"},"create_time":2,"content":{"parts":["second"]}}},"a":{"message":{"author":{"role":"user"},"create_time":1,"content":{"parts":["first"]}}}}}]}'
                )

            conversations = load_chat_export(sample_path)
            self.assertEqual(len(conversations), 1)
            self.assertEqual(conversations[0].messages, ("user: first", "assistant: second"))

    def test_ingest_chat_export_preflights_duplicates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sample_path = f"{temp_dir}/simple.json"
            with open(sample_path, "w", encoding="utf-8") as handle:
                handle.write('[{"id":"conv-1","title":"One","messages":["hello"]}]')

            out = ingest_chat_export(sample_path, temp_dir, max_attempts=2)
            self.assertEqual(out["task_ids"], ["ingest:conv-1"])

            with self.assertRaises(ValueError):
                ingest_chat_export(sample_path, temp_dir, max_attempts=2)

            store = FileTaskStore(temp_dir)
            self.assertEqual(len(store.list_tasks()), 1)


if __name__ == "__main__":
    unittest.main()
