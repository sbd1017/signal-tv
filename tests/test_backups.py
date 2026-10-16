"""Backup providers (tvapp/backups.py): the same channel on a second subscription."""
import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path

import httpx

from tvapp import backups
from tests.test_state_api import settings


class Names(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(backups.norm_name("UK: SKY SPORTS MAIN EVENT ᴴᴰ ◉"), backups.norm_name("UK| Sky Sports Main Event FHD"))
        self.assertNotEqual(backups.norm_name("UK: Sky Sports 1"), backups.norm_name("UK: Sky Sports 2"))


class Matching(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = settings(Path(self.tmp.name))
        row = {"IPTV_PROVIDER_TYPE": "xtream", "XTREAM_BASE_URL": "http://b.example:8080", "XTREAM_USERNAME": "u2", "XTREAM_PASSWORD": "p2"}
        self.b = backups.Backup(self.s, row, 0)

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, rows):
        def handler(request):
            action = request.url.params.get("action")
            if not action:
                return httpx.Response(200, json={"user_info": {"auth": 1, "status": "Active"}})
            return httpx.Response(200, json=rows)

        async def go():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
                await self.b.refresh(c)
        asyncio.run(go())

    def test_same_service_ids_then_guide_id_then_name(self):
        self.load([{"stream_id": 11, "name": "UK: SKY SPORTS MAIN EVENT FHD", "epg_channel_id": "skymain.uk"},
                   {"stream_id": 12, "name": "UK: BBC ONE HD", "epg_channel_id": ""},
                   {"stream_id": 13, "name": "UK: ITV1 HD", "epg_channel_id": ""},
                   {"stream_id": 14, "name": "UK: ITV1 SD", "epg_channel_id": ""}])
        self.assertEqual(self.b.summary()["channels"], 4)
        url = lambda sid: f"http://b.example:8080/live/u2/p2/{sid}.ts"      # noqa: E731
        self.assertEqual(self.b.match({"kind": "live", "native": "11", "name": "UK: SKY SPORTS MAIN EVENT ᴴᴰ"}), url(11), "same id, same name")
        self.assertEqual(self.b.match({"kind": "live", "native": "999", "name": "Sky Main", "epg": "SKYMAIN.uk"}), url(11), "by guide id")
        self.assertEqual(self.b.match({"kind": "live", "native": "500", "name": "UK| BBC One ◉"}), url(12), "by name")
        self.assertIsNone(self.b.match({"kind": "live", "native": "501", "name": "UK: ITV1"}), "two ITV1s: neither")
        self.assertIsNone(self.b.match({"kind": "live", "native": "12", "name": "UK: Channel 4"}), "same id, another channel")

    def test_stored_privately_and_failures_remembered(self):
        backups.save(self.s.state_dir, [{"IPTV_PROVIDER_TYPE": "m3u", "IPTV_M3U_URL": "http://x/list.m3u"}])
        p = backups.path_for(self.s.state_dir)
        self.assertEqual(oct(p.stat().st_mode & 0o777), "0o600")
        self.assertEqual(json.loads(p.read_text())[0]["label"], "Backup")
        all_ = backups.Backups(self.s)
        self.assertTrue(all_)
        self.assertFalse(all_.prefer_backup("l_1"))
        all_.main_failed("l_1")
        self.assertTrue(all_.prefer_backup("l_1"))
        all_.failed["l_1"] = time.time() - 16 * 60
        self.assertFalse(all_.prefer_backup("l_1"), "for 15 minutes only")
        backups.save(self.s.state_dir, [])
        self.assertFalse(backups.Backups(self.s))


if __name__ == "__main__":
    unittest.main()
