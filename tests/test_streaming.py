import json
import unittest

from api.streaming import run_with_progress


class StreamingTests(unittest.TestCase):
    def test_error_identifies_the_active_stage_and_logs_traceback(self) -> None:
        def work(progress):
            progress("insights", completed=3, total=8)
            raise TypeError("unsupported operand")

        with self.assertLogs("api.streaming", level="ERROR") as logs:
            events = [json.loads(line) for line in run_with_progress(work)]

        self.assertEqual(events[0]["name"], "insights")
        self.assertEqual(events[1]["event"], "error")
        self.assertEqual(events[1]["detail"], "insights: unsupported operand")
        self.assertIn("failed during stage insights", logs.output[0])


if __name__ == "__main__":
    unittest.main()
