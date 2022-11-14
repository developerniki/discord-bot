import asyncio
import io
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import discord
import humanize
from discord import ui, ButtonStyle, Interaction, Embed, TextChannel, User, CategoryChannel, Message
from discord.ext import commands, tasks
from emoji import emojize

from database import TicketRequest, TicketSettingsStore, TicketStore, TicketRequestStore, TicketCooldownStore
from slimbot import SlimBot, tools

_logger = logging.getLogger(__name__)


class TicketSystem(commands.Cog, name='Ticket System'):
    """Allows server members to request tickets from staff."""

    def __init__(self, bot: SlimBot) -> None:
        self.bot = bot
        self.ticket_settings_store = TicketSettingsStore(self.bot.config.db_file)
        self.ticket_store = TicketStore(self.bot.config.db_file)
        self.ticket_request_store = TicketRequestStore(self.bot.config.db_file)
        self.ticket_cooldown_store = TicketCooldownStore(self.bot.config.db_file)
        self._views_added = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self.bot.wait_until_ready()

        if not self._views_added:
            ticket_request_view = TicketRequestView(self)
            self.bot.add_view(ticket_request_view)

            ticket_request_modal = TicketRequestModal(self)
            self.bot.add_view(ticket_request_modal)

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
            if channel is not None:
                await channel.delete(reason='rejected ticket request channel due for deletion')
            await self.ticket_request_store.remove_channel(channel_id)

    @commands.hybrid_group()
    @commands.has_guild_permissions(manage_channels=True)
    async def ticket(self, ctx):
        pass

    @ticket.command()
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
            reason=f'create ticket for user {tools.user_string(member)}',
        )
        await channel.set_permissions(
            ctx.guild.get_member(ticket.user_id),
            read_messages=True,
            send_messages=True,
        )

        # Update the ticket with the channel id.
        await self.ticket_store.set_channel(ticket=ticket, channel_id=channel.id)

        # Describe why this channel was opened.
        member = ctx.guild.get_member(ticket.user_id)
        description = f'This ticket has been created by {ctx.author.mention} for user {member.mention}. '
        if ticket.reason:
            description += f'They have given the following reason:\n{tools.quote_message(ticket.reason)}\n\n'
        description += 'To close this ticket use `/ticket close`. ' \
                       'To add another user to the ticket use `/ticket add <@user>`.'
        embed = Embed(title=f'Ticket #{ticket.id}', description=description, color=discord.Color.yellow(),
                      timestamp=datetime.now(timezone.utc))
        file = discord.File(self.bot.config.img_dir / 'accepted_ticket.png', filename='image.png')
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
        file = discord.File(self.bot.config.img_dir / 'accepted_ticket.png', filename='image.png')
        embed.set_thumbnail(url='attachment://image.png')
        await request_channel.send(embed=embed, file=file)

        # Notify the user that the ticket has been created.
        await ctx.send(f"Successfully created a ticket at channel {channel.mention}.", ephemeral=True)

    @ticket.command()
    async def close(self, ctx: commands.Context) -> None:
        """Close the ticket."""
        if await self.ticket_store.is_ticket_channel(ctx.channel.id):
            # Notify everyone present that the ticket is being closed.
            await ctx.send(
                f'Closing the ticket {ctx.channel.mention} and generating the logs. This might take a while.'
            )

            # Fetch all messages. # TODO Also store images.
            log = [message async for message in ctx.channel.history(limit=None, oldest_first=True)]
            log_dict = [
                {
                    'message_id': message.id,
                    'author_id': message.author.id,
                    'author_name': f'{message.author.name}#{message.author.discriminator}',
                    'created_at': round(message.created_at.timestamp()),
                    'message': message.content,
                    'embeds': [embed.to_dict() for embed in message.embeds],
                    'references': message.reference.message_id if message.reference else None,
                    'reactions': [reaction.emoji for reaction in message.reactions]
                }
                for message in log
            ]

            # Fetch the ticket before closing it.
            ticket = await self.ticket_store.get_ticket_by_channel_id(ctx.channel.id)

            # Store the decision to close the ticket and the log in the database.
            await self.ticket_store.close(ticket=ticket, log=json.dumps(log_dict))

            # If a log channel exists, store the log there.
            ticket_log_channel_id = await self.ticket_settings_store.get_log_channel_id(ctx.guild.id)
            ticket_log_channel = ctx.guild.get_channel(ticket_log_channel_id)
            if ticket_log_channel is not None:
                time_fmt = '%Y-%m-%d %H:%M:%S'
                created_at = datetime.fromtimestamp(ticket.created_at).strftime(time_fmt)
                closed_at = datetime.fromtimestamp(ticket.closed_at).strftime(time_fmt)

                ticket_user = self.bot.get_user(ticket.user_id)
                header = f'Transcript of ticket #{ticket.id}, created at {created_at} for ' \
                         f'user {tools.user_string(ticket_user)}'
                if ticket.reason:
                    header += f' with reason "{ticket.reason}" '
                header += f'and closed at {closed_at}\n'

                txt_log = [header]

                for message in log:
                    message: Message
                    created_at = message.created_at.strftime(time_fmt)
                    author = tools.user_string(message.author)
                    content = message.content.strip()
                    embeds = [json.dumps(embed.to_dict(), separators=(',', ':')) for embed in message.embeds]
                    embeds = '\n'.join(embeds)
                    cur_line = f'[{created_at}] {author}: {content}'
                    if embeds:
                        cur_line += f'\n{embeds}'
                    txt_log.append(cur_line)

                txt_log = '\n'.join(txt_log)
                await ticket_log_channel.send(
                    content=f'Ticket log #{ticket.id}',
                    file=discord.File(fp=io.StringIO(txt_log), filename=f'ticket_log{ticket.id}.txt'),
                )

            # Delete the ticket channel.
            await ctx.channel.delete(reason='closing ticket')
        elif await self.ticket_request_store.is_ticket_request_channel(ctx.channel.id):
            # Notify everyone present that the channel is being closed.
            await ctx.send(f'Closing the ticket request.')

            # Delete the channel.
            await ctx.channel.delete(reason='manually closing rejected ticket request channel')

            # Remove the channel from the database so it is marked as cleaned up.
            await self.ticket_request_store.remove_channel(ctx.channel.id)
        else:
            await ctx.send(f'{ctx.channel.mention} is not a ticket channel!', ephemeral=True)

    @ticket.command()
    async def button(self, ctx: commands.Context) -> None:
        """Create a ticket request button."""
        channel_id = await self.ticket_settings_store.get_request_channel_id(ctx.guild.id)
        channel = channel_id and ctx.guild.get_channel(channel_id)
        if channel is None:
            await ctx.send('Cannot create a button. First, set a ticket request channel.', ephemeral=True)
        else:
            ticket_request_view = TicketRequestView(self)
            await ctx.channel.send(view=ticket_request_view)
            await ctx.send(f'Created the ticket request button with target channel {channel.mention}.', ephemeral=True)

    @ticket.command()
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

    @ticket.command()
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

    @ticket.command()
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

    @ticket.command()
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

    @ticket.command()
    async def requestchannel(self, ctx: commands.Context, channel: Optional[TextChannel]) -> None:
        """Get or set the ticket request channel, depending on whether `channel` is present."""
        if channel is None:
            channel_id = await self.ticket_settings_store.get_request_channel_id(ctx.guild.id)
            channel = channel_id and ctx.guild.get_channel(channel_id)
            if channel is None:
                await ctx.send(f'The ticket request channel is not configured yet.', ephemeral=True)
            else:
                await ctx.send(f'The ticket request channel is {channel.mention}.', ephemeral=True)
        else:
            await self.ticket_settings_store.set_request_channel_id(guild_id=ctx.guild.id, channel_id=channel.id)
            await ctx.send(f'The ticket request channel has been set to {channel.mention}.', ephemeral=True)

    @ticket.command()
    async def logchannel(self, ctx: commands.Context, channel: Optional[TextChannel]) -> None:
        """Get or set the ticket log channel, depending on whether `channel` is present."""
        if channel is None:
            channel_id = await self.ticket_settings_store.get_log_channel_id(ctx.guild.id)
            channel = channel_id and ctx.guild.get_channel(channel_id)
            if channel is None:
                await ctx.send(f'The ticket log channel is not configured yet.', ephemeral=True)
            else:
                await ctx.send(f'The ticket log channel is {channel.mention}.', ephemeral=True)
        else:
            await self.ticket_settings_store.set_log_channel_id(guild_id=ctx.guild.id, channel_id=channel.id)
            await ctx.send(f'The ticket log channel has been set to {channel.mention}.', ephemeral=True)

    @ticket.command()
    async def cooldown(self, ctx: commands.Context, user: Optional[User], cooldown_in_secs: Optional[int]) -> None:
        """Get or set the guild's or user's ticket request cooldown, depending on which arguments are present."""
        if cooldown_in_secs is not None and cooldown_in_secs < 0:
            cooldown_in_secs = 0

        if user is None:
            if cooldown_in_secs is None:
                cooldown_in_secs = await self.ticket_settings_store.get_guild_cooldown(guild_id=ctx.guild.id)
                cooldown = humanize.naturaldelta(cooldown_in_secs) if cooldown_in_secs != 0 else 'nothing'
                if cooldown_in_secs == 0:
                    msg = 'The guild currently does not have a ticket cooldown.'
                else:
                    msg = f"The guild's ticket cooldown is {cooldown}."
                await ctx.send(msg, ephemeral=True)
            else:
                await self.ticket_settings_store.set_guild_cooldown(guild_id=ctx.guild.id,
                                                                    cooldown_in_secs=cooldown_in_secs)
                await ctx.send(f"Successfully set the guild's ticket cooldown to {cooldown_in_secs} seconds.",
                               ephemeral=True)
        else:
            if cooldown_in_secs is None:
                cooldown_in_secs = await self.ticket_cooldown_store.get_remaining_cooldown(guild_id=ctx.guild.id,
                                                                                           user_id=user.id)
                if cooldown_in_secs == 0:
                    msg = f"{user.mention} currently does not have a ticket cooldown."
                else:
                    msg = f"{user.mention}'s ticket cooldown is {humanize.naturaldelta(cooldown_in_secs)}."
                await ctx.send(msg, ephemeral=True)
            else:
                # Reset cooldowns of current tickets first.
                await self.ticket_cooldown_store.reset_user_cooldown(guild_id=ctx.guild.id, user_id=user.id)
                if cooldown_in_secs > 0:  # If the cooldown is 0, we don't need to set it.
                    await self.ticket_cooldown_store.set_user_cooldown(guild_id=ctx.guild.id, user_id=user.id,
                                                                       cooldown_in_secs=cooldown_in_secs)
                await ctx.send(f"Successfully set {user.mention}'s ticket cooldown to {cooldown_in_secs} seconds.",
                               ephemeral=True)

    @ticket.command(hidden=True)
    async def clear(self, ctx: commands.Context, user: User) -> None:
        """WARNING: Only use when something is broken. Close tickets and reject pending requests for `user`."""
        # TODO Deactivate ticket notification views.
        # TODO Store logs.
        # Close all open tickets and delete the corresponding channels.
        channel_ids = await self.ticket_store.close_all_user(guild_id=ctx.guild.id, user_id=user.id)
        for channel_id in channel_ids:
            channel = channel_id and ctx.guild.get_channel(channel_id)
            if channel is not None:
                await channel.delete(reason='closing ticket')

        # Reject all pending ticket requests.
        await self.ticket_request_store.reject_all_user(guild_id=ctx.guild.id, user_id=user.id)
        await ctx.send(f'Closed open tickets and rejected pending ticket requests for {user.mention}.', ephemeral=True)


class TicketRequestView(ui.View):
    """A button that allows a user to request a new ticket."""

    def __init__(self, ticket_system: TicketSystem) -> None:
        super().__init__(timeout=None)
        self.ts = ticket_system

    async def interaction_check(self, interaction: Interaction) -> bool:
        request_channel_id = await self.ts.ticket_settings_store.get_request_channel_id(interaction.guild_id)
        request_channel = request_channel_id and interaction.guild.get_channel(request_channel_id)

        if request_channel is None:
            _logger.info(
                f'{interaction.user} clicked the ticket request button but the ticket request channel is not '
                'configured yet.'
            )
            await interaction.response.send_message(
                'Could not open a ticket request as a ticket request channel has not been configured.',
                ephemeral=True
            )
            return False
        elif await self.ts.ticket_store.num_open(interaction.guild_id, interaction.user.id) > 0:
            _logger.info(f'{interaction.user} clicked the ticket request button but already has an open ticket.')
            await interaction.response.send_message(
                'Could not open a ticket request as you already have an open ticket. Please try again later.',
                ephemeral=True
            )
            return False
        elif await self.ts.ticket_request_store.num_pending(interaction.guild_id, interaction.user.id) > 0:
            _logger.info(
                f'{interaction.user} clicked the ticket request button but still has a pending ticket request.'
            )
            await interaction.response.send_message(
                'Could not open a ticket request as you already have a pending ticket request. Please try again later.',
                ephemeral=True
            )
            return False
        elif await self.ts.ticket_cooldown_store.get_remaining_cooldown(interaction.guild_id, interaction.user.id) > 0:
            _logger.info(f'{interaction.user} clicked the ticket request button but a cooldown is still in effect.')
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
        _logger.info(f'{interaction.user} requested a ticket.')
        request_ticket_modal = TicketRequestModal(self.ts)
        await interaction.response.send_modal(request_ticket_modal)


class TicketRequestModal(ui.Modal, title='Ticket Request'):
    """Asks the user for a description of what they want to talk about and notifies the staff."""

    def __init__(self, ticket_system: TicketSystem) -> None:
        super().__init__(timeout=None, custom_id='request_ticket_modal')
        self.ts = ticket_system
        self.reason_txt_input = ui.TextInput(
            label='What do you want to talk about (optional)?',
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=2000,
            custom_id='request_ticket_text_input'
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

        _logger.info(f'{interaction.user} submitted a ticket request. The reason is: {self.reason_txt_input.value}')

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
        file = discord.File(self.ts.bot.config.img_dir / 'accept_reject.png', filename='image.png')
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
            _logger.warning(
                f'{interaction.user} tried to accept or reject a ticket request but lack the appropriate permissions.'
            )
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
            ticket_member = interaction.guild.get_member(ticket.user_id)
            await channel.set_permissions(
                ticket_member,
                read_messages=True,
                send_messages=True
            )

            # Update the ticket with the channel id.
            await self.ts.ticket_store.set_channel(ticket=ticket, channel_id=channel.id)

            # Describe why this channel was opened.
            description = f'This ticket has been created at the request of {ticket_member.mention}. '
            if ticket.reason:
                description += f'They wanted to talk about the following:\n{tools.quote_message(ticket.reason)}\n\n'
            description += 'To close this ticket use `/ticket close`. ' \
                           'To add another user to the ticket use `/ticket add @<user>`.'
            embed = Embed(title=f'Ticket #{ticket.id}', description=description, color=discord.Color.yellow(),
                          timestamp=datetime.now(timezone.utc))
            file = discord.File(self.ts.bot.config.img_dir / 'accepted_ticket.png', filename='image.png')
            embed.set_thumbnail(url='attachment://image.png')
            await channel.send(embed=embed, file=file)

            _logger.info(f'{interaction.user} accepted the ticket request for user {tools.user_string(ticket_member)} '
                         f'with reason {ticket.reason}.')

            # Store the decision to accept the ticket in the database.
            await self.ts.ticket_request_store.accept(ticket_request=self.ticket_request, ticket=ticket)

            # Stop listening to the view and deactivate it.
            self.stop()
            self.remove_item(self.reject_button)
            self.accept_button.label = f'{self.accept_button.label}ed'
            self.accept_button.disabled = True

            # Edit the original embed.
            embed = interaction.message.embeds[0]
            embed.title += ' [ACCEPTED]'
            embed.colour = discord.Color.green()
            file = discord.File(self.ts.bot.config.img_dir / 'accepted_ticket.png', filename='image.png')
            embed.set_thumbnail(url='attachment://image.png')

            # Send the edited embed and view.
            await interaction.response.edit_message(embed=embed, attachments=[file], view=self)

            # Notify the user that the action is complete and a channel has been created.
            await interaction.followup.send(
                f'{interaction.user.mention} accepted the ticket request. '
                f'Therefore, a channel has been created at {channel.mention}.',
                ephemeral=False
            )

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
            ticket_member = interaction.guild.get_member(self.ticket_request.user_id)
            await channel.set_permissions(
                ticket_member,
                read_messages=True,
                send_messages=False
            )

            # Store the decision to reject the ticket in the database.
            await self.ts.ticket_request_store.reject(self.ticket_request)

            # Update the ticket request with the channel id.
            await self.ts.ticket_request_store.set_channel(ticket_request=self.ticket_request, channel_id=channel.id)

            # Describe why this channel was opened.
            description = f'The ticket created at the request of {ticket_member.mention} has been ' \
                          '__**rejected**__. Therefore, this channel only serves to inform them of this ' \
                          'decision. It will be auto-deleted in ~24 hours. '
            if self.ticket_request.reason:
                description += 'Originally, the user wanted to talk about the following:\n' \
                               f'{tools.quote_message(self.ticket_request.reason)}\n\n'
            description += 'To close this channel use `/ticket close`. ' \
                           'To add another user to the channel use `/ticket add <@user>`.'
            embed = Embed(title=f'Ticket Request #{self.ticket_request.id} [REJECTED]',
                          description=description,
                          color=discord.Color.red(),
                          timestamp=datetime.now(timezone.utc))
            file = discord.File(self.ts.bot.config.img_dir / 'rejected_ticket.png', filename='image.png')
            embed.set_thumbnail(url='attachment://image.png')
            await channel.send(embed=embed, file=file)

            _logger.info(f'{interaction.user} rejected the ticket request for user {tools.user_string(ticket_member)} '
                         f'with reason {self.ticket_request.reason}.')

            # Store the decision to reject the ticket request in the database and apply a cooldown to the user.
            await self.ts.ticket_request_store.reject(ticket_request=self.ticket_request)
            cooldown_in_secs = await self.ts.ticket_settings_store.get_guild_cooldown(guild_id=interaction.guild_id)
            await self.ts.ticket_cooldown_store.set_user_cooldown(
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
                cooldown_in_secs=cooldown_in_secs
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
            file = discord.File(self.ts.bot.config.img_dir / 'rejected_ticket.png', filename='image.png')
            embed.set_thumbnail(url='attachment://image.png')

            # Send the edited embed and view.
            await interaction.response.edit_message(embed=embed, attachments=[file], view=self)

            # Notify the user that the action is complete and a channel has been created.
            await interaction.followup.send(
                f'{interaction.user.mention} rejected the ticket request. '
                f'Therefore, a channel has been created at {channel.mention}.',
                ephemeral=False
            )


async def setup(bot: SlimBot) -> None:
    await bot.add_cog(TicketSystem(bot))
