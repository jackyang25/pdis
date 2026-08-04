import json
import re
import threading
import unittest
from pathlib import Path

import api.streaming as streaming
from api.streaming import QUEUED_STAGE, run_with_progress


def drain(work) -> list:
    """Run a stream to completion and return its decoded events."""
    return [json.loads(line) for line in run_with_progress(work)]


class StreamingTests(unittest.TestCase):
    def test_error_identifies_the_active_stage_and_logs_traceback(self) -> None:
        def work(progress):
            progress("insights", completed=3, total=8)
            raise TypeError("unsupported operand")

        with self.assertLogs("api.streaming", level="ERROR") as logs:
            events = drain(work)

        self.assertEqual(events[0]["name"], "insights")
        self.assertEqual(events[1]["event"], "error")
        self.assertEqual(events[1]["detail"], "insights: unsupported operand")
        self.assertIn("failed during stage insights", logs.output[0])


class RunCapacityTests(unittest.TestCase):
    """The gateway admits a bounded number of concurrent pipeline runs.

    One run peaks near half a gigabyte, so an unbounded gateway lets concurrent
    uploads exceed the instance; the OOM kill then takes every tool down, not
    only the tool that was overloaded.
    """

    def setUp(self) -> None:
        self._slots = streaming._run_slots
        self.addCleanup(setattr, streaming, "_run_slots", self._slots)

    def use_capacity(self, limit: int) -> None:
        streaming._run_slots = threading.Semaphore(limit)

    def test_a_run_beyond_the_cap_waits_instead_of_starting(self) -> None:
        self.use_capacity(1)
        holder_entered = threading.Event()
        release_holder = threading.Event()
        second_started = threading.Event()

        def holder(progress):
            progress("grading")
            holder_entered.set()
            release_holder.wait(timeout=5)
            return {"who": "holder"}

        def waiter(progress):
            second_started.set()
            return {"who": "waiter"}

        # Daemon threads: if the cap ever stops releasing, the waiter blocks
        # forever, and a non-daemon thread would hang the suite after the
        # assertion below had already reported the fault.
        holder_events: list = []
        first = threading.Thread(
            target=lambda: holder_events.extend(drain(holder)), daemon=True
        )
        first.start()
        self.assertTrue(holder_entered.wait(timeout=5), "the first run never started")

        waiter_events: list = []
        second = threading.Thread(
            target=lambda: waiter_events.extend(drain(waiter)), daemon=True
        )
        second.start()

        # The queued run must not touch `work` while the cap is spent. Its own
        # body would set this, so the flag is the direct observation.
        self.assertFalse(
            second_started.wait(timeout=0.5),
            "a run started while the concurrency cap was fully spent",
        )

        release_holder.set()
        first.join(timeout=5)
        second.join(timeout=5)

        self.assertTrue(second_started.is_set(), "the queued run never ran")
        self.assertEqual(waiter_events[0], {"event": "stage", "name": QUEUED_STAGE})
        self.assertEqual(waiter_events[-1]["result"], {"who": "waiter"})
        # Waiting is not a stage of the work, so the run that never waited
        # reports exactly the events it always did.
        self.assertEqual(holder_events[0], {"event": "stage", "name": "grading"})

    def test_a_failed_run_returns_its_slot(self) -> None:
        self.use_capacity(1)

        def failing(progress):
            raise RuntimeError("provider unavailable")

        with self.assertLogs("api.streaming", level="ERROR"):
            self.assertEqual(drain(failing)[-1]["event"], "error")

        # Probed without blocking: a slot lost to a failed run retires capacity
        # until the next restart, and asserting that by starting another run
        # would hang the suite instead of reporting the leak.
        recovered = streaming._run_slots.acquire(blocking=False)
        self.assertTrue(recovered, "a failed run did not return its capacity")
        streaming._run_slots.release()

        def succeeding(progress):
            return {"ok": True}

        events = drain(succeeding)
        self.assertEqual(events[0]["event"], "complete")
        self.assertNotIn(QUEUED_STAGE, [event.get("name") for event in events])

    def test_an_uncontended_run_announces_no_queue(self) -> None:
        def work(progress):
            progress("parsing")
            return {"ok": True}

        names = [event.get("name") for event in drain(work)]
        self.assertEqual(names, ["parsing", None])


class SingleWorkerTests(unittest.TestCase):
    def test_the_image_runs_one_uvicorn_worker(self) -> None:
        """The cap counts runs in one process, so worker count is part of it.

        `--workers 4` would multiply MAX_CONCURRENT_RUNS by four with no error
        anywhere, reintroducing the memory ceiling this cap exists to hold.
        """
        dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"
        command = dockerfile.read_text(encoding="utf-8")
        self.assertIn("uvicorn api.main:app", command)
        self.assertIsNone(
            re.search(r"--workers|WEB_CONCURRENCY", command),
            "a multi-worker command multiplies MAX_CONCURRENT_RUNS; make the cap "
            "shared before allowing more than one worker",
        )


if __name__ == "__main__":
    unittest.main()
