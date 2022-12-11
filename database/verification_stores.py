import time
from pathlib import Path
from typing import Optional, List

import aiosqlite

from database import BaseStore
from slimbot import tools


class VerificationRequest:
    """The in-memory representation of a user verification in the database."""

    def __init__(self, user_verification_id: int, guild_id: int, user_id: int, join_channel_id: int,
                 join_message_id: int, verified: bool, joined_at: int, closed_at: Optional[int], age: str,
                 gender: str) -> None:
        self.id = user_verification_id
        self.guild_id = guild_id
        self.user_id = user_id
        self.join_channel_id = join_channel_id
        self.join_message_id = join_message_id
        self.verified = verified
        self.joined_at = joined_at
        self.closed_at = closed_at
        self.age = age
        self.gender = gender


class VerificationSettingStore(BaseStore):
    """Handles database access with the `Settings` table for settings related to the verification system."""

    def __init__(self, db_file: Path) -> None:
        super().__init__(db_file)

    async def get_join_channel_id(self, guild_id: int) -> int:
        channel_id = await self.get_setting(guild_id, 'join_channel_id')
        return channel_id

    async def set_join_channel_id(self, guild_id: int, channel_id: int) -> None:
        await self.set_setting(guild_id, 'join_channel_id', channel_id)

    async def get_join_message(self, guild_id: int) -> str:
        message = await self.get_setting(guild_id, 'join_message')
        return message

    async def set_join_message(self, guild_id: int, message: str) -> None:
        await self.set_setting(guild_id, 'join_message', message)

    async def get_welcome_channel_id(self, guild_id: int) -> int:
        channel_id = await self.get_setting(guild_id, 'welcome_channel_id')
        return channel_id

    async def set_welcome_channel_id(self, guild_id: int, channel_id: int) -> None:
        await self.set_setting(guild_id, 'welcome_channel_id', channel_id)

    async def get_welcome_message(self, guild_id: int) -> str:
        message = await self.get_setting(guild_id, 'welcome_message')
        return message

    async def set_welcome_message(self, guild_id: int, message: str) -> None:
        await self.set_setting(guild_id, 'welcome_message', message)

    async def get_request_channel_id(self, guild_id: int) -> int:
        channel_id = await self.get_setting(guild_id, 'verification_request_channel_id')
        return channel_id

    async def set_request_channel_id(self, guild_id: int, channel_id: int) -> None:
        await self.set_setting(guild_id, 'verification_request_channel_id', channel_id)

    async def get_verification_role_id(self, guild_id: int) -> int:
        channel_id = await self.get_setting(guild_id, 'verification_role_id')
        return channel_id

    async def set_verification_role_id(self, guild_id: int, role_id: int) -> None:
        await self.set_setting(guild_id, 'verification_role_id', role_id)

    async def get_adult_role_id(self, guild_id: int) -> int:
        channel_id = await self.get_setting(guild_id, 'adult_role_id')
        return channel_id

    async def set_adult_role_id(self, guild_id: int, role_id: int) -> None:
        await self.set_setting(guild_id, 'adult_role_id', role_id)


class VerificationRequestStore(BaseStore):
    """Handles database access with the `VerificationRequests` table."""

    def __init__(self, db_file: Path) -> None:
        super().__init__(db_file)

    async def create(self, guild_id: int, user_id: int, join_channel_id: int,
                     join_message_id: int, age: str, gender: str) -> VerificationRequest:
        async with aiosqlite.connect(self.db_file) as con:
            statement = """INSERT INTO
                        VerificationRequests(
                            guild_id,
                            user_id,
                            join_channel_id,
                            join_message_id,
                            verified,
                            joined_at,
                            age,
                            gender
                        )
                        VALUES (?, ?, ?, ?, FALSE, ?, ?, ?)
                        """
            joined_at = tools.unix_seconds_from_discord_snowflake_id(join_message_id)
            cur = await con.execute(statement,
                                    (guild_id, user_id, join_channel_id, join_message_id, joined_at, age, gender))
            await con.commit()
            user_verification = VerificationRequest(user_verification_id=cur.lastrowid, guild_id=guild_id,
                                                    user_id=user_id, join_channel_id=join_channel_id,
                                                    join_message_id=join_message_id, verified=False,
                                                    joined_at=joined_at, closed_at=None)
            return user_verification

    async def close(self, verification_request: VerificationRequest, verified: bool) -> None:
        async with aiosqlite.connect(self.db_file) as con:
            statement = 'UPDATE VerificationRequests SET verified=?, closed_at=? WHERE id=?'
            closed_at = round(time.time())
            await con.execute(statement, (verified, closed_at, verification_request.id))
            await con.commit()
            verification_request.verified = verified

    async def get_pending(self) -> List[VerificationRequest]:
        async with aiosqlite.connect(self.db_file) as con:
            statement = 'SELECT * FROM VerificationRequests WHERE closed_at IS NULL'
            cur = await con.execute(statement)
            verification_requests_raw = await cur.fetchall()
            verification_requests = [
                VerificationRequest(
                    user_verification_id=user_verification_id,
                    guild_id=guild_id,
                    user_id=user_id,
                    join_channel_id=join_channel_id,
                    join_message_id=join_message_id,
                    verified=verified,
                    joined_at=joined_at,
                    closed_at=closed_at,
                    age=age,
                    gender=gender
                )
                for
                user_verification_id, guild_id, user_id, join_channel_id, join_message_id, verified, joined_at, closed_at, age, gender
                in verification_requests_raw
            ]
            return verification_requests

    async def get_join_message_id(self, guild_id: int, user_id: int) -> int:
        async with aiosqlite.connect(self.db_file) as con:
            statement = """SELECT join_message_id FROM VerificationRequests WHERE guild_id=? AND user_id=?"""
            cur = await con.execute(statement, (guild_id, user_id))
            join_message_id = cur.fetchone()
            join_message_id = join_message_id and join_message_id[0]
            return join_message_id
