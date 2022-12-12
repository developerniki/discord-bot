import time
from pathlib import Path
from typing import Optional, List

import aiosqlite

from database import BaseStore
from slimbot import tools


class VerificationRequest:
    """The in-memory representation of a verification request in the database."""

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


class ActiveVerificationMessage:
    """The in-memory representation of an active verification message in the database."""

    def __init__(self, message_id: int, guild_id: int, user_id: int, channel_id: int, created_at: int) -> None:
        self.id = message_id
        self.guild_id = guild_id
        self.user_id = user_id
        self.channel_id = channel_id
        self.created_at = created_at


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
            verification_request = VerificationRequest(user_verification_id=cur.lastrowid, guild_id=guild_id,
                                                       user_id=user_id, join_channel_id=join_channel_id,
                                                       join_message_id=join_message_id, verified=False,
                                                       joined_at=joined_at, closed_at=None, age=age, gender=gender)
            return verification_request

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


class ActiveVerificationMessageStore(BaseStore):
    """Handles database access with the `VerificationMessages` table."""

    def __init__(self, db_file: Path) -> None:
        super().__init__(db_file)

    async def create(self, message_id: int, guild_id: int, user_id: int, channel_id: int) -> ActiveVerificationMessage:
        async with aiosqlite.connect(self.db_file) as con:
            statement = """INSERT INTO
                        ActiveVerificationMessages(
                            id,
                            guild_id,
                            user_id,
                            channel_id,
                            created_at
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """
            created_at = tools.unix_seconds_from_discord_snowflake_id(message_id)
            await con.execute(statement, (message_id, guild_id, user_id, channel_id, created_at))
            await con.commit()
            active_verification_message = ActiveVerificationMessage(message_id=message_id, guild_id=guild_id,
                                                                    user_id=user_id, channel_id=channel_id,
                                                                    created_at=created_at)
            return active_verification_message

    async def get(self, guild_id: int, user_id: int) -> List[ActiveVerificationMessage]:
        async with aiosqlite.connect(self.db_file) as con:
            statement = 'SELECT * FROM ActiveVerificationMessages WHERE guild_id=? AND user_id=?'
            cur = await con.execute(statement, (guild_id, user_id))
            active_verification_messages_raw = await cur.fetchall()
            active_verification_messages = [
                ActiveVerificationMessage(
                    message_id=message_id, guild_id=guild_id, user_id=user_id, channel_id=channel_id,
                    created_at=created_at
                )
                for message_id, guild_id, user_id, channel_id, created_at in active_verification_messages_raw
            ]
            return active_verification_messages

    async def num(self, guild_id: int, user_id: int) -> None:
        async with aiosqlite.connect(self.db_file) as con:
            statement = """SELECT COUNT(*) FROM ActiveVerificationMessages WHERE guild_id=? AND user_id=?"""
            cur = await con.execute(statement, (guild_id, user_id))
            num_active = await cur.fetchone()
            num_active = num_active and num_active[0]
            return num_active

    async def delete(self, guild_id: int, user_id: int) -> None:
        """Delete all active messages of `user` in `guild`."""
        async with aiosqlite.connect(self.db_file) as con:
            statement = """DELETE FROM ActiveVerificationMessages WHERE guild_id=? AND user_id=?"""
            await con.execute(statement, (guild_id, user_id))
            await con.commit()
