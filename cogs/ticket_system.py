import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

import aiosqlite
import discord
import humanize
from discord import ui, ButtonStyle, Interaction, Embed, TextChannel, User, CategoryChannel
from discord.ext import commands, tasks
from emoji import emojize

import tools
from main import BaseStore, SlimBot

_logger = logging.getLogger(__name__)


class TicketSystem(commands.GroupCog, name='ticket'):
    """A group cog that implements a ticket system allowing server members to request tickets from staff."""

    def __init__(self, bot: SlimBot) -> None:
        self.bot = bot
        self.ticket_settings_store = TicketSettingsStore(self.bot.db_loc)
        self.ticket_store = TicketStore(self.bot.db_loc)
        self.ticket_request_store = TicketRequestStore(self.bot.db_loc)
        self.ticket_cooldown_store = TicketCooldownStore(self.bot.db_loc)
        self._views_added = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self.bot.wait_until_ready()

        if not self._views_added:
            ticket_request_view = TicketRequestView(self)
            self.bot.add_view(ticket_request_view)

            pending_ticket_requests = await self.ticket_request_store.get_pending()
            for ticket_request in pending_ticket_requests:
                ticket_notification_view = TicketNotificationView(ticket_system=self, ticket_request=ticket_request)
                self.bot.add_view(ticket_notification_view)

            self._views_added = True

    @tasks.loop(hours=1)
    async def close_due_ticket_request_channels(self):
        channel_ids = await self.ticket_request_store.get_due_channel_ids(seconds=24 * 60 * 60)
        for channel_id in channel_ids:
            channel = self.bot.get_channel(channel_id)
            await channel.delete(reason='rejected ticket request channel due for deletion')
            await self.ticket_request_store.remove_channel(channel_id)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def create(self, ctx: commands.Context, member: User, reason: Optional[str] = None) -> None:
        """Create a new ticket."""
        # Get the ticket request channel.
        request_channel_id = await self.ticket_settings_store.get_request_channel_id(ctx.guild.id)
        if request_channel_id is None:
            await ctx.send(
                'Cannot create a ticket. First, set a ticket request channel to denote the ticket category.',
                ephemeral=True
            )
            return
        request_channel = ctx.guild.get_channel(request_channel_id)

        # Create a new ticket.
        ticket = await self.ticket_store.create(
            guild_id=ctx.guild.id,
            user_id=member.id,
            reason=reason,
        )

        # Create the ticket text channel and set channel permissions accordingly.
        channel = await ctx.guild.create_text_channel(
            f'ticket {ticket.id}',
            category=request_channel.category,
            reason=f'create ticket for user {tools.user_string(ctx.author)}',
        )
        await channel.set_permissions(
            ctx.guild.get_member(ticket.user_id),
            read_messages=True,
            send_messages=True
        )

        # Update the ticket with the channel id.
        await self.ticket_store.set_channel(ticket=ticket, channel_id=channel.id)

        # Describe why this channel was opened.
        member = ctx.guild.get_member(ticket.user_id)
        description = f'This ticket has been created by {ctx.author.mention} for user {member.mention}. '
        if ticket.reason:
            description += f'They have given the following reason:\n{tools.quote_message(ticket.reason)}\n\n'
        description += 'To close this ticket use `/ticket close`. ' \
                       'To add another user to the ticket use `/ticket add_user <@user>`.'
        embed = Embed(title=f'Ticket #{ticket.id}', description=description, color=discord.Color.yellow(),
                      timestamp=datetime.now(timezone.utc))
        file = discord.File(self.bot.img_dir / 'accepted_ticket.png', filename='image.png')
        embed.set_thumbnail(url='attachment://image.png')
        await channel.send(embed=embed, file=file)

        # Log the ticket creation.
        description = f'{ctx.author.mention} has created a ticket for {member.mention} at {channel.mention}.'
        if reason:
            description += f' They have given the following reason:\n{tools.quote_message(reason)}'
        embed = Embed(title='Manual Ticket Creation', description=description, color=discord.Color.yellow(),
                      timestamp=datetime.now(timezone.utc))
        embed.set_author(name=tools.user_string(member),
                         url=f'https://discordapp.com/users/{member.id}',
                         icon_url=member.display_avatar)
        file = discord.File(self.bot.img_dir / 'accepted_ticket.png', filename='image.png')
        embed.set_thumbnail(url='attachment://image.png')
        await request_channel.send(embed=embed, file=file)

        # Notify the user that the ticket has been created.
        await ctx.send(f"Successfully created a ticket at channel {channel.mention}.", ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def close(self, ctx: commands.Context) -> None:
        """Close the ticket."""
        if await self.ticket_store.is_ticket_channel(ctx.channel.id):
            await ctx.send(f'Closing the ticket {ctx.channel.mention}.', ephemeral=True)
            # TODO Store a log in the database.
            await ctx.channel.delete(reason='closing ticket')
            await self.ticket_store.close_by_channel(channel_id=ctx.channel.id, log=None)
        elif await self.ticket_request_store.is_ticket_request_channel(ctx.channel.id):
            await ctx.send(f'Closing the ticket request.', ephemeral=True)
            await ctx.channel.delete(reason='manually closing rejected ticket request channel')
            await self.ticket_request_store.remove_channel(ctx.channel.id)
        else:
            await ctx.send(f'{ctx.channel.mention} is not a ticket channel!', ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def request_button(self, ctx: commands.Context) -> None:
        """Create a ticket request button."""
        channel_id = await self.ticket_settings_store.get_request_channel_id(ctx.guild.id)
        channel = channel_id and ctx.guild.get_channel(channel_id)
        if channel is None:
            await ctx.send('Cannot create a button. First, set a ticket request channel.', ephemeral=True)
        else:
            ticket_request_view = TicketRequestView(self)
            await ctx.channel.send(view=ticket_request_view)
            await ctx.send(f'Created the ticket request button with target channel {channel.mention}.', ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def clear_all(self, ctx: commands.Context, user: User) -> None:
        """Close open tickets and reject pending ticket requests for `user` without updating notifications."""
        # TODO Deactivate ticket notification views.
        # Close all open tickets and delete the corresponding channels.
        channel_ids = await self.ticket_store.close_all_user(guild_id=ctx.guild.id, user_id=user.id)
        for channel_id in channel_ids:
            channel = channel_id and ctx.guild.get_channel(channel_id)
            if channel is not None:
                await channel.delete(reason='closing ticket')

        # Reject all pending ticket requests.
        await self.ticket_request_store.reject_all_user(guild_id=ctx.guild.id, user_id=user.id)
        await ctx.send(f'Closed open tickets and rejected pending ticket requests for {user.mention}.', ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def add(self, ctx: commands.Context, user: discord.Member, allow_send_messages: bool = True) -> None:
        """Add `user` to this ticket channel."""
        is_ticket_channel = await self.ticket_store.is_ticket_channel(ctx.channel.id)
        is_ticket_request_channel = await self.ticket_request_store.is_ticket_request_channel(ctx.channel.id)
        if is_ticket_channel or is_ticket_request_channel:
            perms = ctx.channel.permissions_for(user)
            if not perms.read_messages:
                await ctx.channel.set_permissions(user, read_messages=True, send_messages=allow_send_messages)
                await ctx.send(
                    f'Added user {user.mention} to this channel {"with" if allow_send_messages else "without"} '
                    'message sending permissions.',
                    ephemeral=False
                )
            else:
                await ctx.send(f'{user.mention} is already added to this channel!', ephemeral=True)
        else:
            await ctx.send(f'{ctx.channel.mention} is not a ticket or request denial channel!', ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def remove(self, ctx: commands.Context, user: discord.Member) -> None:
        """Remove `user` from this ticket channel."""
        is_ticket_channel = await self.ticket_store.is_ticket_channel(ctx.channel.id)
        is_ticket_request_channel = await self.ticket_request_store.is_ticket_request_channel(ctx.channel.id)
        if is_ticket_channel or is_ticket_request_channel:
            perms = ctx.channel.permissions_for(user)
            if perms.read_messages:
                await ctx.channel.set_permissions(user, read_messages=False, send_messages=False)
                await ctx.send(f'Removed user {user.mention} from this channel.', ephemeral=False)
            else:
                await ctx.send(f'{user.mention} is already removed from this channel!', ephemeral=True)
        else:
            await ctx.send(f'{ctx.channel.mention} is not a ticket or request denial channel!', ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def mute(self, ctx: commands.Context, user: discord.Member) -> None:
        """Mute `user` in this ticket channel."""
        is_ticket_channel = await self.ticket_store.is_ticket_channel(ctx.channel.id)
        is_ticket_request_channel = await self.ticket_request_store.is_ticket_request_channel(ctx.channel.id)
        if is_ticket_channel or is_ticket_request_channel:
            perms = ctx.channel.permissions_for(user)
            if perms.read_messages:
                if perms.send_messages:
                    await ctx.channel.set_permissions(user, read_messages=True, send_messages=False)
                    await ctx.send(f'Muted user {user.mention} in this ticket channel.', ephemeral=False)
                else:
                    await ctx.send(f'{user.mention} is already muted!', ephemeral=True)
            else:
                await ctx.send(f'{user.mention} was not yet added to this channel!', ephemeral=True)
        else:
            await ctx.send(f'{ctx.channel.mention} is not a ticket or request denial channel!', ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def unmute(self, ctx: commands.Context, user: discord.Member) -> None:
        """Unmute `user` in this ticket channel."""
        is_ticket_channel = await self.ticket_store.is_ticket_channel(ctx.channel.id)
        is_ticket_request_channel = await self.ticket_request_store.is_ticket_request_channel(ctx.channel.id)
        if is_ticket_channel or is_ticket_request_channel:
            perms = ctx.channel.permissions_for(user)
            if perms.read_messages:
                if not perms.send_messages:
                    await ctx.channel.set_permissions(user, read_messages=True, send_messages=True)
                    await ctx.send(f'Unmuted user {user.mention} in this channel.', ephemeral=False)
                else:
                    await ctx.send(f'{user.mention} is already unmuted!', ephemeral=True)
            else:
                await ctx.send(f'{user.mention} was not yet added to this channel!', ephemeral=True)
        else:
            await ctx.send(f'{ctx.channel.mention} is not a ticket or request denial channel!', ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def get_request_channel(self, ctx: commands.Context) -> None:
        """Get the ticket request channel."""
        channel_id = await self.ticket_settings_store.get_request_channel_id(ctx.guild.id)
        channel = channel_id and ctx.guild.get_channel(channel_id)
        if channel is None:
            await ctx.send(f'The ticket request channel is not configured yet.', ephemeral=True)
        else:
            await ctx.send(f'The ticket request channel is {channel.mention}.', ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def set_request_channel(self, ctx: commands.Context, channel: TextChannel) -> None:
        """Set the ticket request channel."""
        await self.ticket_settings_store.set_request_channel_id(guild_id=ctx.guild.id, channel_id=channel.id)
        await ctx.send(f'The ticket request channel has been set to {channel.mention}.', ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def get_remaining_user_cooldown(self, ctx: commands.Context, user: User) -> None:
        """Get `user`'s remaining ticket request cooldown."""
        cooldown_in_secs = await self.ticket_cooldown_store.get_remaining_cooldown(guild_id=ctx.guild.id,
                                                                                   user_id=user.id)
        if cooldown_in_secs == 0:
            msg = f"{user.mention} currently does not have a ticket cooldown."
        else:
            msg = f"{user.mention}'s ticket cooldown is {humanize.naturaldelta(cooldown_in_secs)}."
        await ctx.send(msg, ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def set_user_cooldown(self, ctx: commands.Context, user: User, cooldown_in_secs: int) -> None:
        """Set `user`'s ticket request cooldown."""
        await self.ticket_cooldown_store.set_user_cooldown(guild_id=ctx.guild.id, user_id=user.id,
                                                           cooldown_in_secs=cooldown_in_secs)
        await ctx.send(f"Successfully set {user.mention}'s ticket cooldown to {cooldown_in_secs} seconds.",
                       ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def reset_user_cooldown(self, ctx: commands.Context, user: User) -> None:
        """Reset `user`'s ticket request cooldown."""
        await self.ticket_cooldown_store.reset_user_cooldown(guild_id=ctx.guild.id, user_id=user.id)
        await ctx.send(f"Successfully reset {user.mention}'s ticket cooldown.", ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def get_guild_cooldown(self, ctx: commands.Context) -> None:
        """Get the guild's ticket request cooldown."""
        cooldown_in_secs = await self.ticket_settings_store.get_guild_cooldown(guild_id=ctx.guild.id)
        cooldown = humanize.naturaldelta(cooldown_in_secs) if cooldown_in_secs != 0 else 'nothing'
        if cooldown_in_secs == 0:
            msg = 'The guild currently does not have a ticket cooldown.'
        else:
            msg = f"The guild's ticket cooldown is {cooldown}."
        await ctx.send(msg, ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def set_guild_cooldown(self, ctx: commands.Context, cooldown_in_secs: int) -> None:
        """Set the guild's ticket request cooldown."""
        await self.ticket_settings_store.set_guild_cooldown(guild_id=ctx.guild.id, cooldown_in_secs=cooldown_in_secs)
        await ctx.send(f"Successfully set the guild's ticket cooldown to {cooldown_in_secs} seconds.", ephemeral=True)


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

    def __init__(self, db_loc: str) -> None:
        super().__init__(db_loc)

    async def get_request_channel_id(self, guild_id: int) -> int:
        channel_id = await self.get_setting(guild_id, 'ticket_request_channel_id')
        return channel_id

    async def set_request_channel_id(self, guild_id: int, channel_id: int) -> None:
        await self.set_setting(guild_id, 'ticket_request_channel_id', channel_id)

    async def get_guild_cooldown(self, guild_id: int) -> int:
        return await self.get_setting(guild_id, 'ticket_cooldown')

    async def set_guild_cooldown(self, guild_id: int, cooldown_in_secs: int) -> None:
        return await self.set_setting(guild_id, 'ticket_cooldown', cooldown_in_secs)


class TicketStore(BaseStore):
    """Handles database access with the `Tickets` table."""

    def __init__(self, db_loc: str) -> None:
        super().__init__(db_loc)

    async def num_open(self, guild_id: int, user_id: int) -> int:
        """Returns the number of open tickets of the user."""
        async with aiosqlite.connect(self.db_loc) as con:
            statement = """SELECT COUNT(*)
                        FROM Tickets
                        WHERE guild_id = ? AND user_id = ? AND status="open"
                        """
            cur = await con.execute(statement, (guild_id, user_id))
            num_open_tickets = await cur.fetchone()
            num_open_tickets = num_open_tickets and num_open_tickets[0]
            return num_open_tickets

    async def is_ticket_channel(self, channel_id: int) -> bool:
        async with aiosqlite.connect(self.db_loc) as con:
            statement = 'SELECT 1 FROM Tickets WHERE channel_id = ?'
            cur = await con.execute(statement, (channel_id,))
            res = await cur.fetchone()
            return res is not None

    async def create(self, guild_id: int, user_id: int, reason: Optional[str] = None) -> Ticket:
        """Create a new `Ticket` with status `open`."""
        async with aiosqlite.connect(self.db_loc) as con:
            statement = """INSERT INTO
                        Tickets(guild_id, user_id, reason, status, created_at)
                        VALUES (?, ?, ?, "open", ?)
                        """
            created_at = int(time.time())
            cur = await con.execute(statement, (guild_id, user_id, reason, created_at))
            await con.commit()
            ticket = Ticket(ticket_id=cur.lastrowid, guild_id=guild_id, user_id=user_id, reason=reason, status="open",
                            channel_id=None, log=None, created_at=created_at, closed_at=None)
            return ticket

    async def set_channel(self, ticket: Ticket, channel_id: Optional[int]) -> None:
        async with aiosqlite.connect(self.db_loc) as con:
            statement = 'UPDATE Tickets SET channel_id=? WHERE id=?'
            await con.execute(statement, (channel_id, ticket.id))
            await con.commit()
            ticket.channel_id = channel_id

    async def close(self, ticket: Ticket, log: Optional[str]) -> None:
        async with aiosqlite.connect(self.db_loc) as con:
            statement = 'UPDATE Tickets SET status="closed", channel_id=NULL, log=?, closed_at=? WHERE id=?'
            await con.execute(statement, (log, int(time.time()), ticket.id))
            await con.commit()
            ticket.status = 'closed'

    async def close_by_channel(self, channel_id: int, log: Optional[str]) -> None:
        async with aiosqlite.connect(self.db_loc) as con:
            statement = 'UPDATE Tickets SET status="closed", channel_id=NULL, log=?, closed_at=? WHERE channel_id=?'
            await con.execute(statement, (log, int(time.time()), channel_id))
            await con.commit()

    async def close_all_user(self, guild_id: int, user_id: int) -> List[int]:
        """Set the status of all the users' open tickets to `closed` and return the associated channel ids."""
        async with aiosqlite.connect(self.db_loc) as con:
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

    async def get_all(self) -> List[Ticket]:
        async with aiosqlite.connect(self.db_loc) as con:
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
        async with aiosqlite.connect(self.db_loc) as con:
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

    def __init__(self, db_loc: str) -> None:
        super().__init__(db_loc)

    async def create(self, guild_id: int, user_id: int, reason: Optional[str]) -> TicketRequest:
        """Create a new `TicketRequest` with status `pending`."""
        async with aiosqlite.connect(self.db_loc) as con:
            statement = """INSERT INTO
                        TicketRequests(guild_id, user_id, reason, status, created_at)
                        VALUES (?, ?, ?, "pending", ?)
                        """
            created_at = int(time.time())
            cur = await con.execute(statement, (guild_id, user_id, reason, created_at))
            await con.commit()
            ticket_request = TicketRequest(ticket_request_id=cur.lastrowid, guild_id=guild_id, user_id=user_id,
                                           ticket_id=None, reason=reason, status='pending', channel_id=None,
                                           created_at=created_at, closed_at=None)
            return ticket_request

    async def is_ticket_request_channel(self, channel_id: int) -> bool:
        async with aiosqlite.connect(self.db_loc) as con:
            statement = 'SELECT 1 FROM TicketRequests WHERE channel_id = ?'
            cur = await con.execute(statement, (channel_id,))
            res = await cur.fetchone()
            return res is not None

    async def set_channel(self, ticket_request: TicketRequest, channel_id: Optional[int]) -> None:
        async with aiosqlite.connect(self.db_loc) as con:
            statement = 'UPDATE TicketRequests SET channel_id=? WHERE id=?'
            await con.execute(statement, (channel_id, ticket_request.id))
            await con.commit()
            ticket_request.channel_id = channel_id

    async def remove_channel(self, channel_id: int) -> None:
        async with aiosqlite.connect(self.db_loc) as con:
            statement = 'UPDATE TicketRequests SET channel_id=NULL WHERE channel_id=?'
            await con.execute(statement, (channel_id,))
            await con.commit()

    async def accept(self, ticket_request: TicketRequest, ticket: Ticket) -> None:
        async with aiosqlite.connect(self.db_loc) as con:
            statement = 'UPDATE TicketRequests SET ticket_id=?, status="accepted", closed_at=? WHERE id=?'
            closed_at = int(time.time())
            await con.execute(statement, (ticket.id, closed_at, ticket_request.id))
            await con.commit()
            ticket_request.status = 'accepted'

    async def reject(self, ticket_request: TicketRequest) -> None:
        async with aiosqlite.connect(self.db_loc) as con:
            statement = 'UPDATE TicketRequests SET status="rejected", closed_at=? WHERE id=?'
            closed_at = int(time.time())
            await con.execute(statement, (closed_at, ticket_request.id))
            await con.commit()
            ticket_request.status = 'rejected'

    async def reject_all_user(self, guild_id: int, user_id: int) -> None:
        """Set the status of all the users' pending ticket requests to `rejected`."""
        async with aiosqlite.connect(self.db_loc) as con:
            statement = """UPDATE TicketRequests
                        SET status="rejected"
                        WHERE guild_id=? AND user_id=? AND status="pending"
                        """
            await con.execute(statement, (guild_id, user_id))
            await con.commit()

    async def delete(self, ticket_request: TicketRequest) -> None:
        async with aiosqlite.connect(self.db_loc) as con:
            statement = 'DELETE FROM TicketRequests WHERE id=?'
            await con.execute(statement, (ticket_request.id,))
            await con.commit()

    async def get_all(self) -> List[TicketRequest]:
        async with aiosqlite.connect(self.db_loc) as con:
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
        async with aiosqlite.connect(self.db_loc) as con:
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
        async with aiosqlite.connect(self.db_loc) as con:
            statement = """SELECT channel_id
                        FROM TicketRequests
                        WHERE status="rejected" AND IFNULL(MAX(rejected_at) - ?, 0) > ?
                        """
            cur = await con.execute(statement, (int(time.time()), seconds))
            due_channel_ids = await cur.fetchall()
            return [channel_id[0] for channel_id in due_channel_ids]

    async def num_pending(self, guild_id: int, user_id: int) -> int:
        """Returns the number of pending ticket requests of the user."""
        async with aiosqlite.connect(self.db_loc) as con:
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

    def __init__(self, db_loc: str) -> None:
        super().__init__(db_loc)

    async def get_remaining_cooldown(self, guild_id: int, user_id: int) -> int:
        """Get the remaining ticket cooldown."""
        async with aiosqlite.connect(self.db_loc) as con:
            statement = """SELECT IFNULL(MAX(cooldown_ends_at) - ?, 0)
                        FROM UserTicketCooldowns
                        WHERE guild_id=? AND user_id = ?"""
            cur = await con.execute(statement, (int(time.time()), guild_id, user_id))
            res = await cur.fetchone()
            res = res[0]
            return res

    async def set_user_cooldown(self, guild_id: int, user_id: int, cooldown_in_secs: int,
                                ticket: Optional[Ticket] = None) -> None:
        """Start a ticket cooldown. Set ticket=None to start a manual cooldown that is not associated with any
        particular ticket.
        """
        ticket_id = None if ticket is None else ticket.id
        async with aiosqlite.connect(self.db_loc) as con:
            cooldown_ends_at = int(time.time()) + cooldown_in_secs
            statement = """INSERT OR REPLACE INTO
                        UserTicketCooldowns(guild_id, user_id, ticket_id, cooldown_ends_at)
                        VALUES (?, ?, ?, ?)"""
            await con.execute(statement, (guild_id, user_id, ticket_id, cooldown_ends_at))
            await con.commit()

    async def reset_user_cooldown(self, guild_id: int, user_id: int) -> None:
        """Reset the ticket cooldown of `user` in `guild` by removing all the cooldowns."""
        async with aiosqlite.connect(self.db_loc) as con:
            statement = """DELETE FROM UserTicketCooldowns WHERE guild_id=? AND user_id=?"""
            await con.execute(statement, (guild_id, user_id))
            await con.commit()


class TicketRequestView(ui.View):
    """A button that allows a user to request a new ticket."""

    def __init__(self, ticket_system: TicketSystem) -> None:
        super().__init__(timeout=None)
        self.ts = ticket_system

    async def interaction_check(self, interaction: Interaction) -> bool:
        request_channel_id = await self.ts.ticket_settings_store.get_request_channel_id(interaction.guild_id)
        request_channel = request_channel_id and interaction.guild.get_channel(request_channel_id)

        if request_channel is None:
            await interaction.response.send_message(
                'Could not open a ticket request as a ticket request channel has not been configured.',
                ephemeral=True
            )
            return False
        elif await self.ts.ticket_store.num_open(interaction.guild_id, interaction.user.id) > 0:
            await interaction.response.send_message(
                'Could not open a ticket request as you already have an open ticket. Please try again later.',
                ephemeral=True
            )
            return False
        elif await self.ts.ticket_request_store.num_pending(interaction.guild_id, interaction.user.id) > 0:
            await interaction.response.send_message(
                'Could not open a ticket request as you already have a pending ticket request. Please try again later.',
                ephemeral=True
            )
            return False
        elif await self.ts.ticket_cooldown_store.get_remaining_cooldown(interaction.guild_id,
                                                                        interaction.user.id) > 0:
            await interaction.response.send_message(
                'Could not open a ticket request as your ticket was rejected recently. Please try again later.',
                ephemeral=True
            )
            return False
        else:
            return True

    @ui.button(
        label='Request Ticket',
        style=ButtonStyle.green,
        emoji=emojize(':bell:'),
        custom_id='request_ticket',
    )
    async def request_ticket(self, interaction: Interaction, _button: ui.Button) -> None:
        request_ticket_modal = TicketRequestModal(self.ts)
        await interaction.response.send_modal(request_ticket_modal)


class TicketRequestModal(ui.Modal, title='Ticket Request'):
    """Asks the user for a description of what they want to talk about and notifies the staff."""

    def __init__(self, ticket_system: TicketSystem) -> None:
        super().__init__()
        self.ts = ticket_system
        self.reason_txt_input = ui.TextInput(
            label='What do you want to talk about (optional)?',
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=2000
        )
        self.add_item(self.reason_txt_input)

    async def interaction_check(self, interaction: Interaction) -> bool:
        request_channel_id = await self.ts.ticket_settings_store.get_request_channel_id(interaction.guild_id)
        request_channel = request_channel_id and interaction.guild.get_channel(request_channel_id)

        if request_channel is None:
            await interaction.response.send_message(
                'Could not open a ticket request as a ticket request channel has not been configured.',
                ephemeral=True
            )
            return False
        elif await self.ts.ticket_store.num_open(interaction.guild_id, interaction.user.id) > 0:
            await interaction.response.send_message(
                'Could not open a ticket request as you already have an open ticket. Please try again later.',
                ephemeral=True
            )
            return False
        elif await self.ts.ticket_request_store.num_pending(interaction.guild_id, interaction.user.id) > 0:
            await interaction.response.send_message(
                'Could not open a ticket request as you already have a pending ticket request. Please try again later.',
                ephemeral=True
            )
            return False
        elif await self.ts.ticket_cooldown_store.get_remaining_cooldown(interaction.guild_id,
                                                                        interaction.user.id) > 0:
            await interaction.response.send_message(
                'Could not open a ticket request as your ticket was rejected recently. Please try again later.',
                ephemeral=True
            )
            return False
        else:
            return True

    async def on_submit(self, interaction: Interaction) -> None:
        request_channel_id = await self.ts.ticket_settings_store.get_request_channel_id(interaction.guild_id)
        request_channel = interaction.guild.get_channel(request_channel_id)

        # Open a new ticket request in the database.
        ticket_request = await self.ts.ticket_request_store.create(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
            reason=self.reason_txt_input.value,
        )

        # Create the ticket notification embed.
        description = f'{interaction.user.mention} has requested a ticket.'
        if self.reason_txt_input.value:
            description += f' They have left the following message:\n{tools.quote_message(self.reason_txt_input.value)}'
        embed = Embed(title=f'Ticket Request #{ticket_request.id}', description=description, color=discord.Color.blue(),
                      timestamp=datetime.now(timezone.utc))
        embed.set_author(name=tools.user_string(interaction.user),
                         url=f'https://discordapp.com/users/{interaction.user.id}',
                         icon_url=interaction.user.display_avatar)
        file = discord.File(self.ts.bot.img_dir / 'accept_reject.png', filename='image.png')
        embed.set_thumbnail(url='attachment://image.png')

        # Create the ticket notification view.
        ticket_notification_view = TicketNotificationView(ticket_system=self.ts, ticket_request=ticket_request)

        # Send the embed and view to the ticket request channel.
        await request_channel.send(embed=embed, file=file, view=ticket_notification_view)

        # Let the user know that the staff has been notified.
        await interaction.response.send_message(
            f'Thanks for your response, {interaction.user.mention}! The staff has been notified.',
            ephemeral=True,
        )


class TicketNotificationView(ui.View):
    """Notifies the staff about a new ticket request and lets them accept or reject it.
    In the first case, creates a new channel. In both cases, notifies the user about the staff decision."""

    def __init__(self, ticket_system: TicketSystem, ticket_request: TicketRequest) -> None:
        super().__init__(timeout=None)
        self.ts = ticket_system
        self.ticket_request = ticket_request
        self.lock = asyncio.Lock()
        self.accept_button = ui.Button(label='Accept', style=ButtonStyle.green, emoji=emojize(':check_mark_button:'),
                                       custom_id=f'accept_ticket_request#{self.ticket_request.id}')
        self.reject_button = ui.Button(label='Reject', style=ButtonStyle.blurple, emoji=emojize(':bell_with_slash:'),
                                       custom_id=f'reject_ticket_request#{self.ticket_request.id}')
        self.accept_button.callback = self.accept_ticket_request
        self.reject_button.callback = self.reject_ticket_request
        self.add_item(self.accept_button)
        self.add_item(self.reject_button)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.guild_permissions.manage_channels:
            return True
        else:
            await interaction.response.send_message('You are not allowed to do this action!')
            return False

    async def accept_ticket_request(self, interaction: Interaction) -> None:
        # The lock and `is_finished()` call ensure that the view is only responded to once.
        async with self.lock:
            if self.is_finished():
                return

            # Create the ticket.
            ticket = await self.ts.ticket_store.create(
                self.ticket_request.guild_id,
                self.ticket_request.user_id,
                self.ticket_request.reason
            )

            # Create the ticket text channel and set permissions accordingly.
            channel = await interaction.guild.create_text_channel(
                f'ticket {ticket.id}',
                category=interaction.channel.category,
                reason=f'create ticket for user {tools.user_string(interaction.user)}',
            )
            await channel.set_permissions(
                interaction.guild.get_member(ticket.user_id),
                read_messages=True,
                send_messages=True
            )

            # Update the ticket with the channel id.
            await self.ts.ticket_store.set_channel(ticket=ticket, channel_id=channel.id)

            # Describe why this channel was opened.
            ticket_member = interaction.guild.get_member(ticket.user_id)
            description = f'This ticket has been created at the request of {ticket_member.mention}. '
            if ticket.reason:
                description += f'They wanted to talk about the following:\n{tools.quote_message(ticket.reason)}\n\n'
            description += 'To close this ticket use `/ticket close`. ' \
                           'To add another user to the ticket use `/ticket adduser <@user>`.'
            embed = Embed(title=f'Ticket #{ticket.id}', description=description, color=discord.Color.yellow(),
                          timestamp=datetime.now(timezone.utc))
            file = discord.File(self.ts.bot.img_dir / 'accepted_ticket.png', filename='image.png')
            embed.set_thumbnail(url='attachment://image.png')
            await channel.send(embed=embed, file=file)

            # Store the decision to accept the ticket in the database.
            await self.ts.ticket_request_store.accept(ticket_request=self.ticket_request, ticket=ticket)

            # Notify the user that the action is complete and a channel has been created.
            await interaction.followup.send(
                f'{interaction.user.mention} accepted the ticket request. '
                f'Therefore, a channel has been created at {channel.mention}.',
                ephemeral=False
            )

            # Stop listening to the view and deactivate it.
            self.stop()
            self.remove_item(self.reject_button)
            self.accept_button.label = f'{self.accept_button.label}ed'
            self.accept_button.disabled = True

            # Edit the original embed.
            embed = interaction.message.embeds[0]
            embed.title += ' [ACCEPTED]'
            embed.colour = discord.Color.green()
            file = discord.File(self.ts.bot.img_dir / 'accepted_ticket.png', filename='image.png')
            embed.set_thumbnail(url='attachment://image.png')

            # Send the edited embed and view.
            await interaction.response.edit_message(embed=embed, attachments=[file], view=self)

    async def reject_ticket_request(self, interaction: Interaction) -> None:
        # `self.lock` and the `self.is_finished()` call ensure that the view is only responded to once.
        async with self.lock:
            if self.is_finished():
                return

            # Create the ticket text channel and set permissions accordingly.
            # NOTE: Even though the ticket was rejected, we create a channel to notify the user of this decision.
            category: CategoryChannel = interaction.channel.category
            channel = await interaction.guild.create_text_channel(
                f'rejected request {self.ticket_request.id}',
                category=category,
                reason=f'reject ticket for user {interaction.user.id}',
            )
            await channel.set_permissions(
                interaction.guild.get_member(self.ticket_request.user_id),
                read_messages=True,
                send_messages=False
            )

            # Store the decision to reject the ticket in the database.
            await self.ts.ticket_request_store.reject(self.ticket_request)

            # Update the ticket request with the channel id.
            await self.ts.ticket_request_store.set_channel(ticket_request=self.ticket_request, channel_id=channel.id)

            # Describe why this channel was opened.
            member = interaction.guild.get_member(self.ticket_request.user_id)
            description = f'The ticket created at the request of {member.mention} has been ' \
                          '__**rejected**__. Therefore, this channel only serves to inform them of this ' \
                          'decision. It will be auto-deleted in ~24 hours. '
            if self.ticket_request.reason:
                description += 'Originally, the user wanted to talk about the following:\n' \
                               f'{tools.quote_message(self.ticket_request.reason)}\n\n'
            description += 'To close this channel use `/ticket close`. ' \
                           'To add another user to the channel use `/ticket adduser <@user>`.'
            embed = Embed(title=f'Ticket Request #{self.ticket_request.id} [REJECTED]',
                          description=description,
                          color=discord.Color.red(),
                          timestamp=datetime.now(timezone.utc))
            file = discord.File(self.ts.bot.img_dir / 'rejected_ticket.png', filename='image.png')
            embed.set_thumbnail(url='attachment://image.png')
            await channel.send(embed=embed, file=file)

            # Store the decision to reject the ticket request in the database and apply a cooldown to the user.
            await self.ts.ticket_request_store.reject(ticket_request=self.ticket_request)
            cooldown_in_secs = await self.ts.ticket_settings_store.get_guild_cooldown(guild_id=interaction.guild_id)
            await self.ts.ticket_cooldown_store.set_user_cooldown(
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
                cooldown_in_secs=cooldown_in_secs
            )

            # Notify the user that the action is complete and a channel has been created.
            await interaction.followup.send(
                f'{interaction.user.mention} rejected the ticket request. '
                f'Therefore, a channel has been created at {channel.mention}.',
                ephemeral=False
            )

            # Stop listening to the view and deactivate it.
            self.stop()
            self.remove_item(self.accept_button)
            self.reject_button.label = f'{self.reject_button.label}ed'
            self.reject_button.disabled = True

            # Edit the original embed.
            embed = interaction.message.embeds[0]
            embed.title += ' [REJECTED]'
            embed.colour = discord.Color.red()
            file = discord.File(self.ts.bot.img_dir / 'rejected_ticket.png', filename='image.png')
            embed.set_thumbnail(url='attachment://image.png')

            # Send the edited embed and view.
            await interaction.response.edit_message(embed=embed, attachments=[file], view=self)


async def setup(bot: SlimBot) -> None:
    await bot.add_cog(TicketSystem(bot))
