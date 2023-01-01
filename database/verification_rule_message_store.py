from pathlib import Path
from typing import List

from database import BaseStore
from slimbot import tools


class VerificationRuleMessage:
    """The in-memory representation of a verification rule message in the database."""

    def __init__(self, id: int, guild_id: int, user_id: int, channel_id: int, created_at: int) -> None:
        self.id = id
        self.guild_id = guild_id
        self.user_id = user_id
        self.channel_id = channel_id
        self.created_at = created_at


class VerificationRuleMessageStore(BaseStore):
    """Handles database access with the `VerificationRuleMessages` table."""

    def __init__(self, db_file: Path) -> None:
        super().__init__(db_file)

    async def create_rule_message(self, message_id: int, guild_id: int, user_id: int, channel_id: int) -> VerificationRuleMessage:
        query = """INSERT INTO
        VerificationRuleMessages(id, guild_id, user_id, channel_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """
        created_at = tools.unix_seconds_from_discord_snowflake_id(message_id)
        params = (message_id, guild_id, user_id, channel_id, created_at)
        await self.execute_query(query, params)
        verification_rule_message = VerificationRuleMessage(id=message_id, guild_id=guild_id, user_id=user_id,
                                                            channel_id=channel_id, created_at=created_at)
        return verification_rule_message

    async def get_rule_messages_by_user(self, guild_id: int, user_id: int) -> List[VerificationRuleMessage]:
        query = 'SELECT * FROM VerificationRuleMessages WHERE guild_id=? AND user_id=?'
        params = (guild_id, user_id)
        return await self.execute_query(query, params, obj_type=VerificationRuleMessage)

    async def get_num_rule_messages_by_user(self, guild_id: int, user_id: int) -> int:
        query = 'SELECT COUNT(*) FROM VerificationRuleMessages WHERE guild_id=? AND user_id=?'
        params = (guild_id, user_id)
        return await self.execute_query(query, params, single_row=True)

    async def delete_rule_messages_by_user(self, guild_id: int, user_id: int) -> None:
        """Delete all verification rule messages of `user` in `guild`."""
        query = 'DELETE FROM VerificationRuleMessages WHERE guild_id=? AND user_id=?'
        params = (guild_id, user_id)
        await self.execute_query(query, params)
