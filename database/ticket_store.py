import time
from pathlib import Path
from typing import Optional, List

from database import BaseStore


class Ticket:
    """The in-memory representation of a ticket in the database."""

    def __init__(self, id: int, guild_id: int, user_id: int, reason: Optional[str], status: str,
                 channel_id: Optional[int], log: Optional[str], created_at: Optional[int],
                 closed_at: Optional[int]) -> None:
        assert status in ('open', 'closed')
        self.id = id
        self.guild_id = guild_id
        self.user_id = user_id
        self.reason = reason
        self.status = status
        self.channel_id = channel_id
        self.log = log
        self.created_at = created_at
        self.closed_at = closed_at


class TicketStore(BaseStore):
    """Handles database access with the `Tickets` table."""

    def __init__(self, db_file: Path) -> None:
        super().__init__(db_file)

    async def create_ticket(self, guild_id: int, user_id: int, reason: Optional[str] = None) -> Ticket:
        """Create a new `Ticket` with status `open`."""
        query = """INSERT INTO
                Tickets(guild_id, user_id, reason, status, created_at)
                VALUES (?, ?, ?, "open", ?)
                """
        created_at = round(time.time())
        params = (guild_id, user_id, reason, created_at)
        _num_rows_affected, lastrowid = await self.execute_query(query, params)
        ticket = Ticket(id=lastrowid, guild_id=guild_id, user_id=user_id, reason=reason, status="open",
                        channel_id=None, log=None, created_at=created_at, closed_at=None)
        return ticket

    async def get_all_tickets(self) -> List[Ticket]:
        query = 'SELECT * FROM Tickets'
        return await self.execute_query(query, obj_type=Ticket)

    async def get_open_tickets(self) -> List[Ticket]:
        query = 'SELECT * FROM Tickets WHERE status="open"'
        return await self.execute_query(query, obj_type=Ticket)

    async def get_num_open_tickets_by_user(self, guild_id: int, user_id: int) -> int:
        query = """SELECT COUNT(*)
                   FROM Tickets
                   WHERE guild_id = ? AND user_id = ? AND status="open"
                   """
        params = (guild_id, user_id)
        return await self.execute_query(query, params, single_row=True)

    async def get_ticket_by_channel(self, channel_id: int) -> Optional[Ticket]:
        query = 'SELECT * FROM Tickets WHERE channel_id=?'
        params = (channel_id,)
        return await self.execute_query(query, params, single_row=True, obj_type=Ticket)

    async def is_ticket_channel(self, channel_id: int) -> bool:
        query = 'SELECT EXISTS(SELECT 1 FROM Tickets WHERE channel_id = ?)'
        params = (channel_id,)
        return await self.execute_query(query, params, single_row=True, obj_type=bool)

    async def close_ticket_by_channel(self, channel_id: int, log: Optional[str]) -> None:
        query = """UPDATE Tickets
                    SET status="closed", channel_id=NULL, log=json(?), closed_at=?
                    WHERE channel_id=?
                    """
        closed_at = round(time.time())
        params = (log, closed_at, channel_id)
        await self.execute_query(query, params)

    async def close_tickets_by_user(self, guild_id: int, user_id: int) -> List[int]:
        """Set the status of all the users' open tickets to `closed` and return the associated channel ids."""
        query = """SELECT channel_id
                    FROM Tickets
                    WHERE guild_id=? AND user_id=? AND status="open"
                    """
        params = (guild_id, user_id)
        open_channel_ids = await self.execute_query(query, params)

        query = """UPDATE Tickets
                    SET status="closed"
                    WHERE guild_id=? AND user_id=? AND status="open"
                    """
        params = (guild_id, user_id)
        await self.execute_query(query, params)

        return open_channel_ids

    async def close_ticket(self, ticket: Ticket, log: Optional[str]) -> None:
        query = 'UPDATE Tickets SET status="closed", channel_id=NULL, log=json(?), closed_at=? WHERE id=?'
        closed_at = round(time.time())
        params = (log, closed_at, ticket.id)
        await self.execute_query(query, params)

        ticket.status = 'closed'
        ticket.closed_at = closed_at

    async def set_ticket_channel(self, ticket: Ticket, channel_id: Optional[int]) -> None:
        query = 'UPDATE Tickets SET channel_id=? WHERE id=?'
        params = (channel_id, ticket.id)
        await self.execute_query(query, params)

        ticket.channel_id = channel_id
