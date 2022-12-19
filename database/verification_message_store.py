from pathlib import Path
from typing import List

from database import BaseStore
from slimbot import tools


class ActiveVerificationMessage:
    """The in-memory representation of an active verification message in the database."""

    def __init__(self, id: int, guild_id: int, user_id: int, channel_id: int, created_at: int) -> None:
        self.id = id
        self.guild_id = guild_id
        self.user_id = user_id
        self.channel_id = channel_id
        self.created_at = created_at


class ActiveVerificationMessageStore(BaseStore):
    """Handles database access with the `VerificationMessages` table."""

    def __init__(self, db_file: Path) -> None:
        super().__init__(db_file)

    async def create_active_verification_message(self, message_id: int, guild_id: int, user_id: int,
                                                 channel_id: int) -> ActiveVerificationMessage:
        query = """INSERT INTO
        ActiveVerificationMessages(id, guild_id, user_id, channel_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """
        created_at = tools.unix_seconds_from_discord_snowflake_id(message_id)
        params = (message_id, guild_id, user_id, channel_id, created_at)
        await self.execute_query(query, params)
        active_verification_message = ActiveVerificationMessage(id=message_id, guild_id=guild_id,
                                                                user_id=user_id, channel_id=channel_id,
                                                                created_at=created_at)
        return active_verification_message

    async def get_active_verification_messages_by_user(self, guild_id: int, user_id: int) -> List[
        ActiveVerificationMessage]:
        query = 'SELECT * FROM ActiveVerificationMessages WHERE guild_id=? AND user_id=?'
        params = (guild_id, user_id)
        return await self.execute_query(query, params, obj_type=ActiveVerificationMessage)

    async def get_num_active_verification_messages_by_user(self, guild_id: int, user_id: int) -> int:
        query = 'SELECT COUNT(*) FROM ActiveVerificationMessages WHERE guild_id=? AND user_id=?'
        params = (guild_id, user_id)
        return await self.execute_query(query, params, single_row=True)

    async def delete_active_verification_messages_by_user(self, guild_id: int, user_id: int) -> None:
        """Delete all active messages of `user` in `guild`."""
        query = 'DELETE FROM ActiveVerificationMessages WHERE guild_id=? AND user_id=?'
        params = (guild_id, user_id)
        await self.execute_query(query, params)
