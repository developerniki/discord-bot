import time
from pathlib import Path
from typing import Optional, List

from database import BaseStore
from slimbot import utils


class VerificationRequest:
    """The in-memory representation of a verification request in the database."""

    def __init__(self, id: int, guild_id: int, user_id: int, join_channel_id: int, join_message_id: int, verified: bool,
                 joined_at: int, closed_at: Optional[int], age: str, gender: str,
                 notification_channel_id: Optional[int]=None, notification_message_id: Optional[int]=None) -> None:
        self.id = id
        self.guild_id = guild_id
        self.user_id = user_id
        self.join_channel_id = join_channel_id
        self.join_message_id = join_message_id
        self.verified = verified
        self.joined_at = joined_at
        self.closed_at = closed_at
        self.age = age
        self.gender = gender
        self.notification_channel_id = notification_channel_id
        self.notification_message_id = notification_message_id


class VerificationRequestStore(BaseStore):
    """Handles database access with the `VerificationRequests` table."""

    def __init__(self, db_file: Path) -> None:
        super().__init__(db_file)

    async def create_verification_request(self, guild_id: int, user_id: int, join_channel_id: int,
                                          join_message_id: int, age: str, gender: str) -> VerificationRequest:
        query = """INSERT INTO
                    VerificationRequests(
                        guild_id, user_id, join_channel_id, join_message_id, verified, joined_at, age, gender,
                        notification_channel_id, notification_message_id
                    )
                    VALUES (?, ?, ?, ?, FALSE, ?, ?, ?, NULL, NULL)
                    """
        joined_at = utils.unix_seconds_from_discord_snowflake_id(join_message_id)
        params = (guild_id, user_id, join_channel_id, join_message_id, joined_at, age, gender)
        _num_rows, lastrowid = await self.execute_query(query, params)
        verification_request = VerificationRequest(id=lastrowid, guild_id=guild_id, user_id=user_id,
                                                   join_channel_id=join_channel_id, join_message_id=join_message_id,
                                                   verified=False, joined_at=joined_at, closed_at=None, age=age,
                                                   gender=gender)
        return verification_request

    async def get_pending_verification_requests(self) -> List[VerificationRequest]:
        query = 'SELECT * FROM VerificationRequests WHERE closed_at IS NULL'
        return await self.execute_query(query, obj_type=VerificationRequest)

    async def get_pending_verification_requests_by_user(self, guild_id: int, user_id: int) -> List[VerificationRequest]:
        query = 'SELECT * FROM VerificationRequests WHERE guild_id = ? AND user_id = ? AND closed_at IS NULL'
        return await self.execute_query(query, (guild_id, user_id), obj_type=VerificationRequest)

    async def get_join_message_id(self, guild_id: int, user_id: int) -> int:
        query = """SELECT join_message_id FROM VerificationRequests WHERE guild_id=? AND user_id=?"""
        params = (guild_id, user_id)
        return await self.execute_query(query, params, single_row=True)

    async def close_verification_request(self, verification_request: VerificationRequest, verified: bool) -> None:
        query = 'UPDATE VerificationRequests SET verified=?, closed_at=? WHERE id=?'
        closed_at = round(time.time())
        params = (verified, closed_at, verification_request.id)
        await self.execute_query(query, params)
        verification_request.verified = verified

    async def set_notification_channel_and_message(self, verification_request: VerificationRequest,
                                                   notification_channel_id: int, notification_message_id: int) -> None:
        query = 'UPDATE VerificationRequests SET notification_channel_id=?, notification_message_id=? WHERE id=?'
        params = (notification_channel_id, notification_message_id, verification_request.id)
        await self.execute_query(query, params)
        verification_request.notification_channel_id = notification_channel_id
        verification_request.notification_message_id = notification_message_id
