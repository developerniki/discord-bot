import logging

import discord
from discord import ui, TextChannel, Member, ButtonStyle, Interaction, Role, SelectOption, Message
from discord.ext import commands
from emoji import emojize

from main import SlimBot, BaseStore

_logger = logging.getLogger(__name__)


class VerificationSystem(commands.GroupCog, name='verify'):
    """A group cog that verifies people and then welcomes them."""

    def __init__(self, bot: SlimBot) -> None:
        self.bot = bot
        self._views_added = False

        self.verification_settings_store = VerificationSettingStore(self.bot.db_loc)
        self._views_added = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self.bot.wait_until_ready()

        if not self._views_added:
            ticket_request_view = VerificationRequestView(self)
            choose_basic_info_view = ChooseBasicInfoView(self)
            self.bot.add_view(ticket_request_view)
            self.bot.add_view(choose_basic_info_view)
            self._views_added = True

    @commands.Cog.listener()
    async def on_member_join(self, member: Member) -> None:
        welcome_channel_id = await self.verification_settings_store.get_welcome_channel_id(member.guild.id)
        welcome_channel = welcome_channel_id and member.guild.get_channel(welcome_channel_id)

        request_channel_id = await self.verification_settings_store.get_request_channel_id(member.guild.id)
        request_channel = request_channel_id and member.guild.get_channel(request_channel_id)

        role_id = await self.verification_settings_store.get_role_id(member.guild.id)
        role = role_id and member.guild.get_role(role_id)

        if None in (welcome_channel, request_channel, role):
            return
        else:
            verification_request_view = VerificationRequestView(self)
            await welcome_channel.send(content=f'Welcome {member.mention}!', view=verification_request_view)

    # TODO delete
    @commands.hybrid_command()
    async def verification_button(self, ctx: commands.Context):
        """Create a verification button."""
        member = ctx.author
        welcome_channel_id = await self.verification_settings_store.get_welcome_channel_id(member.guild.id)
        welcome_channel = welcome_channel_id and member.guild.get_channel(welcome_channel_id)

        request_channel_id = await self.verification_settings_store.get_request_channel_id(member.guild.id)
        request_channel = request_channel_id and member.guild.get_channel(request_channel_id)

        role_id = await self.verification_settings_store.get_role_id(member.guild.id)
        role = role_id and member.guild.get_role(role_id)

        if None in (welcome_channel, request_channel, role):
            return
        else:
            verification_request_view = VerificationRequestView(self)
            await ctx.send(content=f'Welcome {member.mention}!', view=verification_request_view)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def get_welcome_channel(self, ctx: commands.Context) -> None:
        """Get the welcome channel."""
        channel_id = await self.verification_settings_store.get_welcome_channel_id(ctx.guild.id)
        channel = channel_id and ctx.guild.get_channel(channel_id)
        if channel is None:
            await ctx.send(f'The welcome channel is not configured yet.', ephemeral=True)
        else:
            await ctx.send(f'The welcome channel is {channel.mention}.', ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def set_welcome_channel(self, ctx: commands.Context, channel: TextChannel) -> None:
        """Set the welcome channel."""
        await self.verification_settings_store.set_welcome_channel_id(guild_id=ctx.guild.id, channel_id=channel.id)
        await ctx.send(f'The welcome channel has been set to {channel.mention}.', ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def get_verification_request_channel(self, ctx: commands.Context) -> None:
        """Get the verification request channel."""
        channel_id = await self.verification_settings_store.get_request_channel_id(ctx.guild.id)
        channel = channel_id and ctx.guild.get_channel(channel_id)
        if channel is None:
            await ctx.send(f'The verification request channel is not configured yet.', ephemeral=True)
        else:
            await ctx.send(f'The verification request channel is {channel.mention}.', ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def set_verification_request_channel(self, ctx: commands.Context, channel: TextChannel) -> None:
        """Set the verification request channel."""
        await self.verification_settings_store.set_request_channel_id(guild_id=ctx.guild.id, channel_id=channel.id)
        await ctx.send(f'The verification request channel has been set to {channel.mention}.', ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def get_verification_role(self, ctx: commands.Context) -> None:
        """Get the verification request role."""
        role_id = await self.verification_settings_store.get_role_id(ctx.guild.id)
        role = role_id and ctx.guild.get_role(role_id)
        if role is None:
            await ctx.send(f'The verification role is not configured yet.', ephemeral=True)
        else:
            await ctx.send(f'The verification role is {role.mention}.', ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def set_verification_role(self, ctx: commands.Context, role: Role) -> None:
        """Set the verification request role."""
        await self.verification_settings_store.set_role_id(guild_id=ctx.guild.id, role_id=role.id)
        await ctx.send(f'The verification request channel has been set to {role.mention}.', ephemeral=True)


class VerificationSettingStore(BaseStore):
    def __init__(self, db_loc: str):
        super().__init__(db_loc)

    async def get_welcome_channel_id(self, guild_id: int) -> int:
        channel_id = await self.get_setting(guild_id, 'welcome_channel_id')
        return channel_id

    async def set_welcome_channel_id(self, guild_id: int, channel_id: int) -> None:
        await self.set_setting(guild_id, 'welcome_channel_id', channel_id)

    async def get_request_channel_id(self, guild_id: int) -> int:
        channel_id = await self.get_setting(guild_id, 'verification_request_channel_id')
        return channel_id

    async def set_request_channel_id(self, guild_id: int, channel_id: int) -> None:
        await self.set_setting(guild_id, 'verification_request_channel_id', channel_id)

    async def get_role_id(self, guild_id: int) -> int:
        channel_id = await self.get_setting(guild_id, 'verified_role_id')
        return channel_id

    async def set_role_id(self, guild_id: int, role_id: int) -> None:
        await self.set_setting(guild_id, 'verified_role_id', role_id)


class VerificationRequestView(ui.View):
    """A button that allows a user to request verification."""

    def __init__(self, verification_system: VerificationSystem) -> None:
        super().__init__(timeout=None)
        self.vs = verification_system

    async def interaction_check(self, interaction: Interaction) -> bool:
        belongs_to = [x.id for x in interaction.message.mentions]
        if interaction.user.id not in belongs_to:
            await interaction.response.send_message('This is not your verification button!', ephemeral=True)
            return False
        else:
            return True

    @ui.button(
        label='Verify me!',
        style=ButtonStyle.green,
        emoji=emojize(':check_mark_button:'),
        custom_id='request_verification',
    )
    async def request_verification(self, interaction: Interaction, _button: ui.Button) -> None:
        choose_basic_info_view = ChooseBasicInfoView(verification_system=self.vs)
        await interaction.response.send_message(view=choose_basic_info_view, ephemeral=True)


class ChooseBasicInfoView(ui.View):
    """Asks the user about their age and gender."""

    def __init__(self, verification_system: VerificationSystem) -> None:
        super().__init__(timeout=None)
        self.vs = verification_system
        self.age_range_select = ui.Select(
            placeholder="What's your age range?",
            options=[
                SelectOption(label='12-15'),
                SelectOption(label='16-17'),
                SelectOption(label='18-29'),
                SelectOption(label='30-39'),
                SelectOption(label='40+'),
            ],
            custom_id='select_age_range'
        )
        self.age_range_select.callback = self.age_range_selected
        self.add_item(self.age_range_select)

        self.gender_select = ui.Select(
            placeholder="What's your gender?",
            options=[
                SelectOption(label='male', emoji=emojize(':male_sign:')),
                SelectOption(label='female', emoji=emojize(':female_sign:')),
                # TODO Use proper non-binary symbol.
                SelectOption(label='non-binary', emoji=emojize(':keycap_0:')),
            ],
            custom_id='select_gender'
        )
        self.gender_select.callback = self.gender_selected
        self.add_item(self.gender_select)

        self.submit_button = ui.Button(
            label='Submit',
            style=ButtonStyle.green,
            emoji=emojize(':check_mark_button:'),
            custom_id='submit_basic_info',
        )
        self.submit_button.callback = self.submit
        self.add_item(self.submit_button)

    async def age_range_selected(self, interaction: Interaction):
        await interaction.response.defer()

    async def gender_selected(self, interaction: Interaction):
        await interaction.response.defer()

    async def submit(self, interaction: Interaction) -> None:
        age_range = self.age_range_select.values
        age_range = age_range and age_range[0]
        gender = self.gender_select.values
        gender = gender and gender[0]

        if not gender or not age_range:
            await interaction.response.send_message(content='Please fill out both fields!', ephemeral=True)

        if interaction.message.reference is not None:
            if interaction.message.reference.cached_message is None:
                channel = self.vs.bot.get_channel(interaction.message.reference.channel_id)
                welcome_message = await channel.fetch_message(interaction.message.reference.message_id)
            else:
                welcome_message = interaction.message.reference.cached_message
        else:
            welcome_message = None

        request_ticket_modal = ChooseAdvancedInfoModal(verification_system=self.vs, age_range=age_range, gender=gender,
                                                       welcome_message=welcome_message)
        await interaction.response.send_modal(request_ticket_modal)
        await interaction.edit_original_response(content='To retry, click the `Verify me!` button again.', view=None)


class ChooseAdvancedInfoModal(ui.Modal, title='Just a few more questions...'):
    """Asks the user about their reason for joining."""

    def __init__(self, verification_system: VerificationSystem, age_range: str, gender: str,
                 welcome_message: Message) -> None:
        super().__init__(timeout=None)
        self.vs = verification_system
        self.age_range = age_range
        assert age_range in ('12-15', '16-17', '18-29', '30-39', '40+')
        assert gender in ('male', 'female', 'non-binary')
        self.gender = gender
        self.welcome_message = welcome_message
        self.join_reason_text_input = ui.TextInput(
            label='Referrer',
            placeholder='How did you find out about this server?',
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        )
        self.additional_info_text_input = ui.TextInput(
            label='Join Reason',
            placeholder='Why are you here?',
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        )

        self.add_item(self.join_reason_text_input)
        self.add_item(self.additional_info_text_input)

    async def on_submit(self, interaction: Interaction) -> None:
        channel_id = await self.vs.verification_settings_store.get_request_channel_id(interaction.guild_id)
        channel = interaction.guild.get_channel(channel_id)

        await channel.send(content=f'age-range: {self.age_range}\n'
                                   f'gender: {self.gender}\n'
                                   f'join-reason: {self.join_reason_text_input.value}\n'
                                   f'additional info: {self.additional_info_text_input.value}')

        view = VerificationRequestView(verification_system=self.vs)
        button = view.children[0]
        button.disabled = True
        button.label = 'Verification Pending . . .'
        await self.welcome_message.edit(view=view)

        await interaction.response.send_message(
            f'Thanks for your response, {interaction.user.mention}! The staff has been notified.',
            ephemeral=True,
        )


# class TicketNotificationView(ui.View):
#     """Notifies the staff about a new ticket request and lets them accept or reject it.
#     In the first case, creates a new channel. In both cases, notifies the user about the staff decision."""
#
#     def __init__(self, ticket_system: TicketSystem, ticket_request: TicketRequest) -> None:
#         super().__init__(timeout=None)
#         self.ts = ticket_system
#         self.ticket_request = ticket_request
#         self.lock = asyncio.Lock()
#         self.accept_button = ui.Button(label='Accept', style=ButtonStyle.green, emoji=emojize(':check_mark_button:'),
#                                        custom_id=f'accept_ticket_request#{self.ticket_request.id}')
#         self.reject_button = ui.Button(label='Reject', style=ButtonStyle.blurple, emoji=emojize(':bell_with_slash:'),
#                                        custom_id=f'reject_ticket_request#{self.ticket_request.id}')
#         self.accept_button.callback = self.accept_ticket_request
#         self.reject_button.callback = self.reject_ticket_request
#         self.add_item(self.accept_button)
#         self.add_item(self.reject_button)
#
#     async def interaction_check(self, interaction: Interaction) -> bool:
#         if interaction.user.guild_permissions.manage_channels:
#             return True
#         else:
#             await interaction.response.send_message('You are not allowed to do this action!')
#             return False
#
#     async def accept_ticket_request(self, interaction: Interaction) -> None:
#         # The lock and `is_finished()` call ensure that the view is only responded to once.
#         async with self.lock:
#             if self.is_finished():
#                 return
#
#             # Stop listening to the view and deactivate it.
#             self.stop()
#             self.remove_item(self.reject_button)
#             self.accept_button.label = f'{self.accept_button.label}ed'
#             self.accept_button.disabled = True
#             await interaction.response.edit_message(view=self)
#
#             # Create the ticket.
#             ticket = await self.ts.ticket_store.create(
#                 self.ticket_request.guild_id,
#                 self.ticket_request.user_id,
#                 self.ticket_request.reason
#             )
#
#             # Create the ticket text channel and set permissions accordingly.
#             channel = await interaction.guild.create_text_channel(
#                 f'Ticket #{ticket.id}',
#                 category=interaction.channel.category,
#                 reason=f'create ticket for user {tools.user_string(interaction.user)}',
#             )
#             await channel.set_permissions(
#                 interaction.guild.get_member(ticket.user_id),
#                 read_messages=True,
#                 send_messages=True
#             )
#
#             # Update the ticket with the channel id.
#             await self.ts.ticket_store.set_channel(ticket=ticket, channel_id=channel.id)
#
#             # Describe why this channel was opened.
#             ticket_user = self.ts.bot.get_user(ticket.user_id)
#             description = f'This ticket has been created at the request of {ticket_user.mention}. '
#             if ticket.reason:
#                 description += f'They wanted to talk about the following:\n{tools.quote_message(ticket.reason)}\n\n'
#             description += 'To close this ticket use `/ticket close`. ' \
#                            'To add another user to the ticket use `/ticket adduser <@user>`.'
#             embed = Embed(title=f'Ticket #{ticket.id}', description=description, color=Color.yellow(),
#                           timestamp=datetime.now(timezone.utc))
#             file = discord.File(self.ts.bot.img_dir / 'accepted_ticket.png', filename='image.png')
#             embed.set_thumbnail(url='attachment://image.png')
#             await channel.send(embed=embed, file=file)
#
#             # Store the decision to accept the ticket in the database.
#             await self.ts.ticket_request_store.accept(ticket_request=self.ticket_request, ticket=ticket)
#
#             # Notify the user that the action is complete and a channel has been created.
#             await interaction.followup.send(
#                 f'{interaction.user.mention} accepted the ticket request. '
#                 f'Therefore, a channel has been created at {channel.mention}.',
#                 ephemeral=False
#             )
#
#             # Edit the original embed.
#             original_response = await interaction.original_response()
#             embed = original_response.embeds[0]
#             embed.title += ' [ACCEPTED]'
#             embed.colour = Color.yellow()
#             file = discord.File(self.ts.bot.img_dir / 'accepted_ticket.png', filename='image.png')
#             embed.set_thumbnail(url='attachment://image.png')
#             await original_response.edit(embed=embed, attachments=[file])
#
#     async def reject_ticket_request(self, interaction: Interaction) -> None:
#         # The lock and `is_finished()` call ensure that the view is only responded to once.
#         async with self.lock:
#             if self.is_finished():
#                 return
#
#             # Stop listening to the view and deactivate it.
#             self.stop()
#             self.remove_item(self.accept_button)
#             self.reject_button.label = f'{self.reject_button.label}ed'
#             self.reject_button.disabled = True
#             await interaction.response.edit_message(view=self)
#
#             # Create the ticket text channel and set permissions accordingly.
#             # NOTE: Even though the ticket was rejected, we create a channel to notify the user of this decision.
#             category: CategoryChannel = interaction.channel.category
#             channel = await interaction.guild.create_text_channel(
#                 f'Rejected #{self.ticket_request.id}',
#                 category=category,
#                 reason=f'reject ticket for user {interaction.user.id}',
#             )
#             await channel.set_permissions(
#                 interaction.guild.get_member(self.ticket_request.user_id),
#                 read_messages=True,
#                 send_messages=False
#             )
#
#             # Store the decision to reject the ticket in the database.
#             await self.ts.ticket_request_store.reject(self.ticket_request)
#
#             # Update the ticket request with the channel id.
#             await self.ts.ticket_request_store.set_channel(ticket_request=self.ticket_request, channel_id=channel.id)
#
#             # Describe why this channel was opened.
#             user = self.ts.bot.get_user(self.ticket_request.user_id)
#             description = f'The ticket created at the request of {user.mention} has been ' \
#                           '__**rejected**__. Therefore, this channel only serves to inform them of this ' \
#                           'decision. It will be auto-deleted in ~24 hours. '
#             if self.ticket_request.reason:
#                 description += 'Originally, the user wanted to talk about the following:\n' \
#                                f'{tools.quote_message(self.ticket_request.reason)}\n\n'
#             description += 'To close this channel use `/ticket close`. ' \
#                            'To add another user to the channel use `/ticket adduser <@user>`.'
#             embed = Embed(title=f'Ticket Request #{self.ticket_request.id} [REJECTED]',
#                           description=description,
#                           color=Color.red(),
#                           timestamp=datetime.now(timezone.utc))
#             file = discord.File(self.ts.bot.img_dir / 'rejected_ticket.png', filename='image.png')
#             embed.set_thumbnail(url='attachment://image.png')
#             await channel.send(embed=embed, file=file)
#
#             # Store the decision to reject the ticket request in the database and apply a cooldown to the user.
#             await self.ts.ticket_request_store.reject(ticket_request=self.ticket_request)
#             cooldown_in_secs = await self.ts.ticket_settings_store.get_guild_cooldown(guild_id=interaction.guild_id)
#             await self.ts.ticket_cooldown_store.set_user_cooldown(
#                 guild_id=interaction.guild_id,
#                 user_id=interaction.user.id,
#                 cooldown_in_secs=cooldown_in_secs
#             )
#
#             # Notify the user that the action is complete and a channel has been created.
#             await interaction.followup.send(
#                 f'{interaction.user.mention} rejected the ticket request. '
#                 f'Therefore, a channel has been created at {channel.mention}.',
#                 ephemeral=False
#             )
#
#             # Edit the original embed.
#             original_response = await interaction.original_response()
#             embed = original_response.embeds[0]
#             embed.title += ' [REJECTED]'
#             embed.colour = Color.red()
#             file = discord.File(self.ts.bot.img_dir / 'rejected_ticket.png', filename='image.png')
#             embed.set_thumbnail(url='attachment://image.png')
#             await original_response.edit(embed=embed, attachments=[file])


async def setup(bot: SlimBot) -> None:
    await bot.add_cog(VerificationSystem(bot))
