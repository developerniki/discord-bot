import time
from pathlib import Path
from typing import Optional, List

from .database import BaseStore
from .ticket_store import Ticket


class TicketRequest:
    """The in-memory representation of a ticket request in the database."""

    def __init__(self, id: int, guild_id: int, user_id: int, ticket_id: Optional[int],
                 reason: Optional[str], status: str, channel_id: Optional[int], created_at: Optional[int],
                 closed_at: Optional[int]) -> None:
        assert status in ('pending', 'accepted', 'rejected')
        self.id = id
        self.guild_id = guild_id
        self.user_id = user_id
        self.ticket_id = ticket_id
        self.reason = reason
        self.status = status
        self.channel_id = channel_id
        self.created_at = created_at
        self.closed_at = closed_at


class TicketRequestStore(BaseStore):
    """Handles database access with the `TicketRequests` table."""

    def __init__(self, db_file: Path) -> None:
        super().__init__(db_file)

    async def create_ticket_request(self, guild_id: int, user_id: int, reason: Optional[str]) -> TicketRequest:
        """Create a new `TicketRequest` with status `pending`."""
        query = """INSERT INTO
                    TicketRequests(guild_id, user_id, reason, status, created_at)
                    VALUES (?, ?, ?, "pending", ?)
                    """
        created_at = round(time.time())
        params = (guild_id, user_id, reason, created_at)
        _rowcount, lastrowid = await self.execute_query(query, params)
        ticket_request = TicketRequest(id=lastrowid, guild_id=guild_id, user_id=user_id, ticket_id=None,
                                       reason=reason, status='pending', channel_id=None, created_at=created_at,
                                       closed_at=None)
        return ticket_request

    async def get_all_ticket_requests(self) -> List[TicketRequest]:
        query = 'SELECT * FROM TicketRequests'
        return await self.execute_query(query, obj_type=TicketRequest)

    async def get_pending_ticket_requests(self) -> List[TicketRequest]:
        query = 'SELECT * FROM TicketRequests WHERE status="pending"'
        return await self.execute_query(query, obj_type=TicketRequest)

    async def get_num_pending_ticket_requests_by_user(self, guild_id: int, user_id: int) -> int:
        query = """SELECT COUNT(*)
                    FROM TicketRequests
                    WHERE guild_id = ? AND user_id = ? AND status="pending"
                    """
        params = (guild_id, user_id)
        return await self.execute_query(query, params, single_row=True)

    async def get_channel_ids_of_due_ticket_requests(self, seconds: int) -> List[int]:
        """Returns the ticket request channels that are due for deletion (`seconds` seconds after rejecting the
        request).
        """
        query = """SELECT channel_id
                    FROM TicketRequests
                    WHERE status="rejected" AND (? - IFNULL(closed_at, 0)) > ?
                    """
        cur_time = round(time.time())
        params = (cur_time, seconds)
        return await self.execute_query(query, params, obj_type=int)

    async def is_ticket_request_channel(self, channel_id: int) -> bool:
        query = 'SELECT EXISTS(SELECT 1 FROM TicketRequests WHERE channel_id = ?)'
        params = (channel_id,)
        return await self.execute_query(query, params, single_row=True, obj_type=bool)

    async def remove_ticket_request_channel(self, channel_id: int) -> None:
        query = 'UPDATE TicketRequests SET channel_id=NULL WHERE channel_id=?'
        params = (channel_id,)
        await self.execute_query(query, params)

    async def reject_ticket_requests_by_user(self, guild_id: int, user_id: int) -> None:
        """Set the status of all the users' pending ticket requests to `rejected`."""
        query = """UPDATE TicketRequests
                    SET status="rejected"
                    WHERE guild_id=? AND user_id=? AND status="pending"
                    """
        params = (guild_id, user_id)
        await self.execute_query(query, params)

    async def set_ticket_channel(self, ticket_request: TicketRequest, channel_id: Optional[int]) -> None:
        query = 'UPDATE TicketRequests SET channel_id=? WHERE id=?'
        params = (channel_id, ticket_request.id)
        await self.execute_query(query, params)
        ticket_request.channel_id = channel_id

    async def delete_ticket_request(self, ticket_request: TicketRequest) -> None:
        query = 'DELETE FROM TicketRequests WHERE id=?'
        params = (ticket_request.id,)
        await self.execute_query(query, params)

    async def accept_ticket_request(self, ticket_request: TicketRequest, ticket: Ticket) -> None:
        query = 'UPDATE TicketRequests SET ticket_id=?, status="accepted", closed_at=? WHERE id=?'
        closed_at = round(time.time())
        params = (ticket.id, closed_at, ticket_request.id)
        await self.execute_query(query, params)
        ticket_request.status = 'accepted'

    async def reject_ticket_request(self, ticket_request: TicketRequest) -> None:
        query = 'UPDATE TicketRequests SET status="rejected", closed_at=? WHERE id=?'
        closed_at = round(time.time())
        params = (closed_at, ticket_request.id)
        await self.execute_query(query, params)
        ticket_request.status = 'rejected'
