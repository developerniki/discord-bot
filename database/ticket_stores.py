import time
from pathlib import Path
from typing import Optional, List

import aiosqlite

from database import BaseStore


class Ticket:
    """The in-memory representation of a ticket in the database."""

    def __init__(self, ticket_id: int, guild_id: int, user_id: int, reason: Optional[str], status: str,
                 channel_id: Optional[int], log: Optional[str], created_at: Optional[int],
                 closed_at: Optional[int]) -> None:
        assert status in ('open', 'closed')
        self.id = ticket_id
        self.guild_id = guild_id
        self.user_id = user_id
        self.reason = reason
        self.status = status
        self.channel_id = channel_id
        self.log = log
        self.created_at = created_at
        self.closed_at = closed_at


class TicketRequest:
    """The in-memory representation of a ticket request in the database."""

    def __init__(self, ticket_request_id: int, guild_id: int, user_id: int, ticket_id: Optional[int],
                 reason: Optional[str], status: str, channel_id: Optional[int], created_at: Optional[int],
                 closed_at: Optional[int]) -> None:
        assert status in ('pending', 'accepted', 'rejected')
        self.id = ticket_request_id
        self.guild_id = guild_id
        self.user_id = user_id
        self.ticket_id = ticket_id
        self.reason = reason
        self.status = status
        self.channel_id = channel_id
        self.created_at = created_at
        self.closed_at = closed_at


class TicketSettingsStore(BaseStore):
    """Handles database access with the `Settings` table for settings related to the ticket system."""

    def __init__(self, db_file: Path) -> None:
        super().__init__(db_file)

    async def get_request_channel_id(self, guild_id: int) -> int:
        channel_id = await self.get_setting(guild_id, 'ticket_request_channel_id')
        return channel_id

    async def set_request_channel_id(self, guild_id: int, channel_id: int) -> None:
        await self.set_setting(guild_id, 'ticket_request_channel_id', channel_id)

    async def get_log_channel_id(self, guild_id: int) -> int:
        channel_id = await self.get_setting(guild_id, 'ticket_log_channel_id')
        return channel_id

    async def set_log_channel_id(self, guild_id: int, channel_id: int) -> None:
        await self.set_setting(guild_id, 'ticket_log_channel_id', channel_id)

    async def get_guild_cooldown(self, guild_id: int) -> int:
        return await self.get_setting(guild_id, 'ticket_cooldown')

    async def set_guild_cooldown(self, guild_id: int, cooldown_in_secs: int) -> None:
        return await self.set_setting(guild_id, 'ticket_cooldown', cooldown_in_secs)


class TicketStore(BaseStore):
    """Handles database access with the `Tickets` table."""

    def __init__(self, db_file: Path) -> None:
        super().__init__(db_file)

    async def num_open(self, guild_id: int, user_id: int) -> int:
        """Returns the number of open tickets of the user."""
        async with aiosqlite.connect(self.db_file) as con:
            statement = """SELECT COUNT(*)
                        FROM Tickets
                        WHERE guild_id = ? AND user_id = ? AND status="open"
                        """
            cur = await con.execute(statement, (guild_id, user_id))
            num_open_tickets = await cur.fetchone()
            num_open_tickets = num_open_tickets and num_open_tickets[0]
            return num_open_tickets

    async def is_ticket_channel(self, channel_id: int) -> bool:
        async with aiosqlite.connect(self.db_file) as con:
            statement = 'SELECT 1 FROM Tickets WHERE channel_id = ?'
            cur = await con.execute(statement, (channel_id,))
            res = await cur.fetchone()
            return res is not None

    async def create(self, guild_id: int, user_id: int, reason: Optional[str] = None) -> Ticket:
        """Create a new `Ticket` with status `open`."""
        async with aiosqlite.connect(self.db_file) as con:
            statement = """INSERT INTO
                        Tickets(guild_id, user_id, reason, status, created_at)
                        VALUES (?, ?, ?, "open", ?)
                        """
            created_at = round(time.time())
            cur = await con.execute(statement, (guild_id, user_id, reason, created_at))
            await con.commit()
            ticket = Ticket(ticket_id=cur.lastrowid, guild_id=guild_id, user_id=user_id, reason=reason, status="open",
                            channel_id=None, log=None, created_at=created_at, closed_at=None)
            return ticket

    async def set_channel(self, ticket: Ticket, channel_id: Optional[int]) -> None:
        async with aiosqlite.connect(self.db_file) as con:
            statement = 'UPDATE Tickets SET channel_id=? WHERE id=?'
            await con.execute(statement, (channel_id, ticket.id))
            await con.commit()
            ticket.channel_id = channel_id

    async def close(self, ticket: Ticket, log: Optional[str]) -> None:
        async with aiosqlite.connect(self.db_file) as con:
            statement = 'UPDATE Tickets SET status="closed", channel_id=NULL, log=json(?), closed_at=? WHERE id=?'
            closed_at = round(time.time())
            await con.execute(statement, (log, closed_at, ticket.id))
            await con.commit()
            ticket.status = 'closed'
            ticket.closed_at = closed_at

    async def close_by_channel(self, channel_id: int, log: Optional[str]) -> None:
        async with aiosqlite.connect(self.db_file) as con:
            statement = """UPDATE Tickets
                        SET status=\"closed\", channel_id=NULL, log=json(?), closed_at=?
                        WHERE channel_id=?
                        """
            await con.execute(statement, (log, round(time.time()), channel_id))
            await con.commit()

    async def close_all_user(self, guild_id: int, user_id: int) -> List[int]:
        """Set the status of all the users' open tickets to `closed` and return the associated channel ids."""
        async with aiosqlite.connect(self.db_file) as con:
            statement = """SELECT channel_id
                        FROM Tickets
                        WHERE guild_id=? AND user_id=? AND status="open"
                        """
            cur = await con.execute(statement, (guild_id, user_id))
            channel_ids = await cur.fetchall()
            channel_ids_where_open = [channel_id[0] for channel_id in channel_ids]

            statement = """UPDATE Tickets
                        SET status="closed"
                        WHERE guild_id=? AND user_id=? AND status="open"
                        """
            await con.execute(statement, (guild_id, user_id))
            await con.commit()

            return channel_ids_where_open

    async def get_ticket_by_channel_id(self, channel_id: int) -> Optional[Ticket]:
        async with aiosqlite.connect(self.db_file) as con:
            statement = 'SELECT * FROM Tickets WHERE channel_id=?'
            cur = await con.execute(statement, (channel_id,))
            ticket_raw = await cur.fetchone()
            if ticket_raw is not None:
                ticket = Ticket(
                    ticket_id=ticket_raw[0],
                    guild_id=ticket_raw[1],
                    user_id=ticket_raw[2],
                    reason=ticket_raw[3],
                    status=ticket_raw[4],
                    channel_id=ticket_raw[5],
                    log=ticket_raw[6],
                    created_at=ticket_raw[7],
                    closed_at=ticket_raw[8]
                )
            else:
                ticket = None
            return ticket

    async def get_all(self) -> List[Ticket]:
        async with aiosqlite.connect(self.db_file) as con:
            statement = 'SELECT * FROM Tickets'
            cur = await con.execute(statement)
            tickets_raw = await cur.fetchall()
            tickets = [
                Ticket(ticket_id=ticket_id,
                       guild_id=guild_id,
                       user_id=user_id,
                       reason=reason,
                       status=status,
                       channel_id=channel_id,
                       log=log,
                       created_at=created_at,
                       closed_at=closed_at)
                for ticket_id, guild_id, user_id, reason, status, channel_id, log, created_at, closed_at
                in tickets_raw
            ]
            return tickets

    async def get_open(self) -> List[Ticket]:
        async with aiosqlite.connect(self.db_file) as con:
            statement = 'SELECT * FROM Tickets WHERE status="open"'
            cur = await con.execute(statement)
            tickets_raw = await cur.fetchall()
            tickets = [
                Ticket(ticket_id=ticket_id,
                       guild_id=guild_id,
                       user_id=user_id,
                       reason=reason,
                       status=status,
                       channel_id=channel_id,
                       log=log,
                       created_at=created_at,
                       closed_at=closed_at)
                for ticket_id, guild_id, user_id, reason, status, channel_id, log, created_at, closed_at
                in tickets_raw
            ]
            return tickets


class TicketRequestStore(BaseStore):
    """Handles database access with the `TicketRequests` table."""

    def __init__(self, db_file: Path) -> None:
        super().__init__(db_file)

    async def create(self, guild_id: int, user_id: int, reason: Optional[str]) -> TicketRequest:
        """Create a new `TicketRequest` with status `pending`."""
        async with aiosqlite.connect(self.db_file) as con:
            statement = """INSERT INTO
                        TicketRequests(guild_id, user_id, reason, status, created_at)
                        VALUES (?, ?, ?, "pending", ?)
                        """
            created_at = round(time.time())
            cur = await con.execute(statement, (guild_id, user_id, reason, created_at))
            await con.commit()
            ticket_request = TicketRequest(ticket_request_id=cur.lastrowid, guild_id=guild_id, user_id=user_id,
                                           ticket_id=None, reason=reason, status='pending', channel_id=None,
                                           created_at=created_at, closed_at=None)
            return ticket_request

    async def is_ticket_request_channel(self, channel_id: int) -> bool:
        async with aiosqlite.connect(self.db_file) as con:
            statement = 'SELECT 1 FROM TicketRequests WHERE channel_id = ?'
            cur = await con.execute(statement, (channel_id,))
            res = await cur.fetchone()
            return res is not None

    async def set_channel(self, ticket_request: TicketRequest, channel_id: Optional[int]) -> None:
        async with aiosqlite.connect(self.db_file) as con:
            statement = 'UPDATE TicketRequests SET channel_id=? WHERE id=?'
            await con.execute(statement, (channel_id, ticket_request.id))
            await con.commit()
            ticket_request.channel_id = channel_id

    async def remove_channel(self, channel_id: int) -> None:
        async with aiosqlite.connect(self.db_file) as con:
            statement = 'UPDATE TicketRequests SET channel_id=NULL WHERE channel_id=?'
            await con.execute(statement, (channel_id,))
            await con.commit()

    async def accept(self, ticket_request: TicketRequest, ticket: Ticket) -> None:
        async with aiosqlite.connect(self.db_file) as con:
            statement = 'UPDATE TicketRequests SET ticket_id=?, status="accepted", closed_at=? WHERE id=?'
            closed_at = round(time.time())
            await con.execute(statement, (ticket.id, closed_at, ticket_request.id))
            await con.commit()
            ticket_request.status = 'accepted'

    async def reject(self, ticket_request: TicketRequest) -> None:
        async with aiosqlite.connect(self.db_file) as con:
            statement = 'UPDATE TicketRequests SET status="rejected", closed_at=? WHERE id=?'
            closed_at = round(time.time())
            await con.execute(statement, (closed_at, ticket_request.id))
            await con.commit()
            ticket_request.status = 'rejected'

    async def reject_all_user(self, guild_id: int, user_id: int) -> None:
        """Set the status of all the users' pending ticket requests to `rejected`."""
        async with aiosqlite.connect(self.db_file) as con:
            statement = """UPDATE TicketRequests
                        SET status="rejected"
                        WHERE guild_id=? AND user_id=? AND status="pending"
                        """
            await con.execute(statement, (guild_id, user_id))
            await con.commit()

    async def delete(self, ticket_request: TicketRequest) -> None:
        async with aiosqlite.connect(self.db_file) as con:
            statement = 'DELETE FROM TicketRequests WHERE id=?'
            await con.execute(statement, (ticket_request.id,))
            await con.commit()

    async def get_all(self) -> List[TicketRequest]:
        async with aiosqlite.connect(self.db_file) as con:
            statement = 'SELECT * FROM TicketRequests'
            cur = await con.execute(statement)
            ticket_requests_raw = await cur.fetchall()
            ticket_requests = [
                TicketRequest(ticket_request_id=ticket_request_id,
                              guild_id=guild_id,
                              user_id=user_id,
                              ticket_id=ticket_id,
                              reason=reason,
                              status=status,
                              channel_id=channel_id,
                              created_at=created_at,
                              closed_at=closed_at)
                for ticket_request_id, guild_id, user_id, ticket_id, reason, status, channel_id, created_at, closed_at
                in ticket_requests_raw
            ]
            return ticket_requests

    async def get_pending(self) -> List[TicketRequest]:
        async with aiosqlite.connect(self.db_file) as con:
            statement = 'SELECT * FROM TicketRequests WHERE status="pending"'
            cur = await con.execute(statement)
            ticket_requests_raw = await cur.fetchall()
            ticket_requests = [
                TicketRequest(ticket_request_id=ticket_request_id,
                              guild_id=guild_id,
                              user_id=user_id,
                              ticket_id=ticket_id,
                              reason=reason,
                              status=status,
                              channel_id=channel_id,
                              created_at=created_at,
                              closed_at=closed_at)
                for ticket_request_id, guild_id, user_id, ticket_id, reason, status, channel_id, created_at, closed_at
                in ticket_requests_raw
            ]
            return ticket_requests

    async def get_due_channel_ids(self, seconds: int) -> List[int]:
        """Returns the ticket request channels that are due for deletion (`seconds` seconds after rejecting the
        request).
        """
        async with aiosqlite.connect(self.db_file) as con:
            statement = """SELECT channel_id
                        FROM TicketRequests
                        WHERE status="rejected" AND (? - IFNULL(closed_at, 0)) > ?
                        """
            cur = await con.execute(statement, (round(time.time()), seconds))
            due_channel_ids = await cur.fetchall()
            return [channel_id[0] for channel_id in due_channel_ids]

    async def num_pending(self, guild_id: int, user_id: int) -> int:
        """Returns the number of pending ticket requests of the user."""
        async with aiosqlite.connect(self.db_file) as con:
            statement = """SELECT COUNT(*)
                        FROM TicketRequests
                        WHERE guild_id = ? AND user_id = ? AND status="pending"
                        """
            cur = await con.execute(statement, (guild_id, user_id))
            num_pending_requests = await cur.fetchone()
            num_pending_requests = num_pending_requests and num_pending_requests[0]
            return num_pending_requests


class TicketCooldownStore(BaseStore):
    """Handles database access with the `UserTicketCooldowns` table."""

    def __init__(self, db_file: Path) -> None:
        super().__init__(db_file)

    async def get_remaining_cooldown(self, guild_id: int, user_id: int) -> int:
        """Get the remaining ticket cooldown."""
        async with aiosqlite.connect(self.db_file) as con:
            statement = """SELECT IFNULL(MAX(cooldown_ends_at) - ?, 0)
                        FROM UserTicketCooldowns
                        WHERE guild_id=? AND user_id = ?"""
            cur = await con.execute(statement, (round(time.time()), guild_id, user_id))
            res = await cur.fetchone()
            res = res[0]
            return res

    async def set_user_cooldown(self, guild_id: int, user_id: int, cooldown_in_secs: int,
                                ticket: Optional[Ticket] = None) -> None:
        """Start a ticket cooldown. Set ticket=None to start a manual cooldown that is not associated with any
        particular ticket. Does not reset any existing ticket cooldowns. For that, see `reset_user_cooldown`.
        """
        ticket_id = None if ticket is None else ticket.id
        async with aiosqlite.connect(self.db_file) as con:
            cooldown_ends_at = round(time.time()) + cooldown_in_secs
            statement = """INSERT OR REPLACE INTO
                        UserTicketCooldowns(guild_id, user_id, ticket_id, cooldown_ends_at)
                        VALUES (?, ?, ?, ?)"""
            await con.execute(statement, (guild_id, user_id, ticket_id, cooldown_ends_at))
            await con.commit()

    async def reset_user_cooldown(self, guild_id: int, user_id: int) -> None:
        """Reset the current ticket cooldown of `user` in `guild` by removing all the cooldowns."""
        async with aiosqlite.connect(self.db_file) as con:
            statement = """DELETE FROM UserTicketCooldowns WHERE guild_id=? AND user_id=?"""
            await con.execute(statement, (guild_id, user_id))
            await con.commit()
