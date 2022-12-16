import time
from pathlib import Path
from typing import Optional

from database import BaseStore
from database.ticket_store import Ticket


class TicketCooldownStore(BaseStore):
    """Handles database access with the `UserTicketCooldowns` table."""

    def __init__(self, db_file: Path) -> None:
        super().__init__(db_file)

    async def get_remaining_cooldown(self, guild_id: int, user_id: int) -> int:
        """Get the remaining ticket cooldown."""
        query = """SELECT IFNULL(MAX(cooldown_ends_at) - ?, 0)
                    FROM UserTicketCooldowns
                    WHERE guild_id=? AND user_id = ?"""
        cur_time = round(time.time())
        params = (cur_time, guild_id, user_id)
        return await self.execute_query(query, params, single_row=True)

    async def set_user_cooldown(self, guild_id: int, user_id: int, cooldown_in_secs: int,
                                ticket: Optional[Ticket] = None) -> None:
        """Start a ticket cooldown. Set ticket=None to start a manual cooldown that is not associated with any
        particular ticket. Does not reset any existing ticket cooldowns. For that, see `reset_user_cooldown`.
        """
        ticket_id = None if ticket is None else ticket.id
        query = """INSERT OR REPLACE INTO
                    UserTicketCooldowns(guild_id, user_id, ticket_id, cooldown_ends_at)
                    VALUES (?, ?, ?, ?)"""
        cooldown_ends_at = round(time.time()) + cooldown_in_secs
        params = (guild_id, user_id, ticket_id, cooldown_ends_at)
        await self.execute_query(query, params)

    async def reset_user_cooldown(self, guild_id: int, user_id: int) -> None:
        """Reset the current ticket cooldown of `user` in `guild` by removing all the cooldowns."""
        query = """DELETE FROM UserTicketCooldowns WHERE guild_id=? AND user_id=?"""
        params = (guild_id, user_id)
        await self.execute_query(query, params)
