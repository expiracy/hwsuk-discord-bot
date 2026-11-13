import asyncio
import os
import unittest
import uuid
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

from motor.motor_asyncio import AsyncIOMotorClient

from tests.support import BotTestCase


@unittest.skipUnless(os.environ.get("TEST_MONGODB_URI"), "Set TEST_MONGODB_URI to an isolated localhost MongoDB replica set")
class DatabaseIntegrationTests(BotTestCase):
    async def test_report_is_removed_at_most_once(self):
        await self.db.reports.insert_one({"message_id":123, "message_content":"Text"})
        module, cog = await self.load_cog("react_report","ReactReport")
        with patch.object(module, "db", self.db):
            results = await asyncio.gather(cog.remove_report_data(123), cog.remove_report_data(123))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(await self.db.reports.count_documents({}), 0)

    async def test_failed_verification_remains_queued_then_success_acknowledges_it(self):
        user_id = (await self.db.users.insert_one({"discord":{"id":"42"}})).inserted_id
        await self.db.queue.insert_one({"ref":user_id})
        module, cog = await self.load_cog("verify","Verify")
        cog.set_verified = AsyncMock(return_value=False)
        with patch.object(module, "db", self.db):
            await cog.monitor_db()
            self.assertEqual(await self.db.queue.count_documents({}), 1)
            cog.set_verified.return_value = True
            await cog.monitor_db()
        self.assertEqual(await self.db.queue.count_documents({}), 0)

    async def test_existing_legacy_report_is_not_duplicated(self):
        await self.db.reports.insert_one({"message_id":123, "message_content":"Existing"})
        module, cog = await self.load_cog("react_report","ReactReport")
        with patch.object(module, "db", self.db):
            self.assertFalse(await cog.save_report_data({"message_id":123,"message_content":"Retry"}))
        self.assertEqual(await self.db.reports.count_documents({}), 1)

    async def asyncSetUp(self):
        await super().asyncSetUp()
        uri = os.environ["TEST_MONGODB_URI"]
        parsed = urlsplit(uri)
        if parsed.scheme != "mongodb" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Database integration tests require an isolated localhost MongoDB")
        self.mongo = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
        self.addCleanup(self.mongo.close)
        await self.mongo.admin.command("ping")
        self.db = self.mongo["hwsuk_tests_" + uuid.uuid4().hex]
        self.addAsyncCleanup(self.mongo.drop_database, self.db.name)

    async def test_parallel_reports_create_one_document(self):
        module, cog = await self.load_cog("react_report", "ReactReport")
        with patch.object(module, "db", self.db):
            results = await asyncio.gather(*(cog.save_report_data({"message_id": 123, "message_content": "Test"}) for _ in range(10)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(await self.db.reports.count_documents({"message_id": 123}), 1)
