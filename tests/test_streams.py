"""Playback job reaper: idle jobs are stopped, and one job failing to stop never ends the reaper."""
import asyncio
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from tvapp.streams import LIVE_IDLE, Engine, Job


def job(jid, idle_for):
    t = time.time() - idle_for
    j = Job(id=jid, key=f"live:{jid}", kind="live", item_id="l_x", dir=Path("/nonexistent"), url="", ua="", ref="")
    j.last_media = j.last_beat = t
    return j


class Reaper(unittest.TestCase):
    def test_one_failing_stop_does_not_stop_the_others(self):
        eng = Engine(SimpleNamespace())
        eng.jobs = {"a": job("a", LIVE_IDLE + 10), "b": job("b", LIVE_IDLE + 10), "c": job("c", 1)}
        stopped = []

        async def stop(jid, why=""):
            if jid == "a":
                raise OSError("kill failed")
            stopped.append(jid)
            eng.jobs.pop(jid)
        eng.stop = stop
        with self.assertLogs("tv", "WARNING") as logs:
            asyncio.run(eng._reap_once(time.time()))
        self.assertEqual(stopped, ["b"])                       # idle b stopped, busy c kept
        self.assertIn("a", eng.jobs)
        self.assertIn("could not be stopped", logs.output[0])


if __name__ == "__main__":
    unittest.main()


class NotLive(unittest.TestCase):
    """A "live" channel that sends a short recording: ffmpeg reads it far faster than real time and
    ends by itself. It is a recording, not a dropped live stream, so it is never restarted."""

    def test_recording(self):
        from tvapp.streams import recording
        clip = ["frame=18000 fps=3509 q=-1.0 Lsize=N/A time=00:10:00.06 bitrate=N/A speed= 117x"]
        self.assertAlmostEqual(recording(clip, []), 600.06, places=1)
        dropped = ["frame=90000 fps=50 q=-1.0 Lsize=N/A time=00:30:00.00 bitrate=N/A speed=1.01x"]
        self.assertEqual(recording(dropped, []), 0)                       # live at real time that dropped
        burst = ["frame=200 fps=900 q=-1.0 Lsize=N/A time=00:00:08.00 bitrate=N/A speed=12x"]
        self.assertEqual(recording(burst, []), 0)                         # a few buffered seconds: too short to tell
        self.assertEqual(recording(["Connection reset by peer"], []), 0)
        self.assertEqual(recording([], [6.0, 7.5]), 60.0)                  # a transcode's progress readings
