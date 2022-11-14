import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import ui, TextChannel, Member, ButtonStyle, Interaction, Role, SelectOption, Message, Embed, User
from discord.ext import commands
from emoji import emojize

from database import VerificationRequest, VerificationSettingStore, VerificationRequestStore
from slimbot import SlimBot, tools

_logger = logging.getLogger(__name__)


class VerificationSystem(commands.Cog, name='Verification System'):
    """Asks new members to verify, notifies staff, assigns a verification role, and welcomes the member."""

    def __init__(self, bot: SlimBot) -> None:
        self.bot = bot
        self._views_added = False

        self.verification_settings_store = VerificationSettingStore(self.bot.config.db_file)
        self.verification_request_store = VerificationRequestStore(self.bot.config.db_file)
        self._views_added = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self.bot.wait_until_ready()

        if not self._views_added:
            verification_request_view = VerificationRequestView(self)
            self.bot.add_view(verification_request_view)

            choose_basic_info_view = ChooseBasicInfoView(self)
            self.bot.add_view(choose_basic_info_view)

            pending_verification_requests = await self.verification_request_store.get_pending()
            for verification_request in pending_verification_requests:
                verification_request_view = VerificationNotificationView(
                    verification_system=self,
                    verification_request=verification_request
                )
                self.bot.add_view(verification_request_view)

            self._views_added = True

    async def __create_verification_button(self, user: User | Member) -> bool:
        """Creates the button to start the verification process for `user`.

        Returns:
            `True` if all necessary channels, messages, and roles are set up, `False` otherwise.
        """
        join_channel_id = await self.verification_settings_store.get_join_channel_id(user.guild.id)
        join_channel = join_channel_id and user.guild.get_channel(join_channel_id)

        join_message = await self.verification_settings_store.get_join_message(user.guild.id)

        welcome_channel_id = await self.verification_settings_store.get_welcome_channel_id(user.guild.id)
        welcome_channel = welcome_channel_id and user.guild.get_channel(welcome_channel_id)

        welcome_message = await self.verification_settings_store.get_welcome_message(user.guild.id)

        request_channel_id = await self.verification_settings_store.get_request_channel_id(user.guild.id)
        request_channel = request_channel_id and user.guild.get_channel(request_channel_id)

        role_id = await self.verification_settings_store.get_verification_role_id(user.guild.id)
        role = role_id and user.guild.get_role(role_id)

        if None in (join_channel, join_message, welcome_channel, welcome_message, request_channel, role):
            _logger.warning('One of the necessary settings is not configured/not configured properly for the '
                            'verification system to work!')
            success = False
            return success
        else:
            _logger.info(f'Making a verification button for {tools.user_string(user)}.')
            verification_request_view = VerificationRequestView(self)
            if '<user>' in join_message:
                join_message = join_message.replace('<user>', user.mention)
            else:
                join_message = f'{user.mention} {join_message}'
            description = join_message
            embed = Embed(title=f'Welcome to {user.guild.name}!', description=description,
                          color=discord.Color.blue(), timestamp=datetime.now(timezone.utc))
            file = discord.File(self.bot.config.img_dir / 'welcome1.png', filename='image.png')
            embed.set_thumbnail(url='attachment://image.png')
            await join_channel.send(embed=embed, file=file, view=verification_request_view)
            success = True
            return success

    @commands.Cog.listener()
    async def on_member_join(self, member: Member) -> None:
        _logger.info(f'{tools.user_string(member)} joined the server!')
        if member.bot:
            _logger.info(f'{tools.user_string(member)} is a bot, so not making a verification button.')
        else:
            await self.__create_verification_button(member)

    @commands.Cog.listener()
    async def on_member_leave(self, member: Member) -> None:
        pass
        # TODO Remove verification request buttons and join message if verification is incomplete.
        # join_message = self.verification_request_store

    @commands.hybrid_group()
    @commands.has_guild_permissions(manage_roles=True, manage_channels=True)
    async def verification(self, ctx):
        pass

    @verification.command()
    async def button(self, ctx: commands.Context, user: User):
        """Create a verification button for `user`."""
        success = await self.__create_verification_button(user)
        if not success:
            await ctx.send('Cannot create a button. First, configure the necessary settings using the '
                           '`/verification setup` command.', ephemeral=True)
        else:
            join_channel_id = await self.verification_settings_store.get_join_channel_id(ctx.guild.id)
            join_channel = join_channel_id and ctx.guild.get_channel(join_channel_id)
            await ctx.send(f'Created a verification button at {join_channel.mention}.', ephemeral=True)

    @verification.command()
    async def setup(self, ctx: commands.Context, join_channel: TextChannel, join_message: str,
                    welcome_channel: TextChannel, welcome_message: str, request_channel: TextChannel,
                    verification_role: Role) -> None:
        """Set up all necessary channels and roles for the verification system to work."""
        await self.verification_settings_store.set_join_channel_id(
            guild_id=ctx.guild.id,
            channel_id=join_channel.id
        )
        await self.verification_settings_store.set_join_message(
            guild_id=ctx.guild.id,
            message=join_message
        )
        await self.verification_settings_store.set_welcome_channel_id(
            guild_id=ctx.guild.id,
            channel_id=welcome_channel.id
        )
        await self.verification_settings_store.set_welcome_message(
            guild_id=ctx.guild.id,
            message=welcome_message
        )
        await self.verification_settings_store.set_request_channel_id(
            guild_id=ctx.guild.id,
            channel_id=request_channel.id
        )
        await self.verification_settings_store.set_verification_role_id(
            guild_id=ctx.guild.id,
            role_id=verification_role.id
        )
        await ctx.send('Everything set up for the verification system to work!', ephemeral=True)

    @verification.command()
    async def joinchannel(self, ctx: commands.Context, channel: Optional[TextChannel]) -> None:
        """Get or set the join channel, depending on whether `channel` is present."""
        if channel is None:
            channel_id = await self.verification_settings_store.get_join_channel_id(ctx.guild.id)
            channel = channel_id and ctx.guild.get_channel(channel_id)
            if channel is None:
                await ctx.send(f'The join channel is not configured yet.', ephemeral=True)
            else:
                await ctx.send(f'The join channel is {channel.mention}.', ephemeral=True)
        else:
            await self.verification_settings_store.set_join_channel_id(guild_id=ctx.guild.id, channel_id=channel.id)
            await ctx.send(f'The join channel has been set to {channel.mention}.', ephemeral=True)

    @verification.command()
    async def joinmessage(self, ctx: commands.Context, *, message: Optional[str]) -> None:
        """Get or set the join message, depending on whether `message` is present."""
        if message is None:
            message = await self.verification_settings_store.get_join_message(ctx.guild.id)  # TODO
            if message is None:
                await ctx.send(f'The join message is not configured yet.', ephemeral=True)
            else:
                await ctx.send(f'The join message is `{message}`.', ephemeral=True)
        else:
            await self.verification_settings_store.set_join_message(guild_id=ctx.guild.id, message=message)
            await ctx.send(f'The join message has been set to `{message}`.', ephemeral=True)

    @verification.command()
    async def welcomechannel(self, ctx: commands.Context, channel: Optional[TextChannel]) -> None:
        """Get or set the welcome channel, depending on whether `channel` is present."""
        if channel is None:
            channel_id = await self.verification_settings_store.get_welcome_channel_id(ctx.guild.id)
            channel = channel_id and ctx.guild.get_channel(channel_id)
            if channel is None:
                await ctx.send(f'The welcome channel is not configured yet.', ephemeral=True)
            else:
                await ctx.send(f'The welcome channel is {channel.mention}.', ephemeral=True)
        else:
            await self.verification_settings_store.set_welcome_channel_id(guild_id=ctx.guild.id,
                                                                          channel_id=channel.id)
            await ctx.send(f'The welcome channel has been set to {channel.mention}.', ephemeral=True)

    @verification.command()
    async def welcomemessage(self, ctx: commands.Context, *, message: Optional[str]) -> None:
        """Get or set the welcome message, depending on whether `message` is present."""
        if message is None:
            message = await self.verification_settings_store.get_welcome_message(ctx.guild.id)
            if message is None:
                await ctx.send(f'The welcome message is not configured yet.', ephemeral=True)
            else:
                await ctx.send(f'The welcome message is `{message}`.', ephemeral=True)
        else:
            await self.verification_settings_store.set_welcome_message(guild_id=ctx.guild.id, message=message)
            await ctx.send(f'The welcome message has been set to `{message}`.', ephemeral=True)

    @verification.command()
    async def requestchannel(self, ctx: commands.Context, channel: Optional[TextChannel]) -> None:
        """Get or set the verification request channel, depending on whether `channel` is present."""
        if channel is None:
            channel_id = await self.verification_settings_store.get_request_channel_id(ctx.guild.id)
            channel = channel_id and ctx.guild.get_channel(channel_id)
            if channel is None:
                await ctx.send(f'The verification request channel is not configured yet.', ephemeral=True)
            else:
                await ctx.send(f'The verification request channel is {channel.mention}.', ephemeral=True)
        else:
            await self.verification_settings_store.set_request_channel_id(guild_id=ctx.guild.id, channel_id=channel.id)
            await ctx.send(f'The verification request channel has been set to {channel.mention}.', ephemeral=True)

    @verification.command()
    async def role(self, ctx: commands.Context, role: Optional[Role]) -> None:
        """Get or set the verification role, depending on whether `role` is present."""
        if role is None:
            role_id = await self.verification_settings_store.get_verification_role_id(ctx.guild.id)
            role = role_id and ctx.guild.get_role(role_id)
            if role is None:
                await ctx.send(f'The verification role is not configured yet.', ephemeral=True)
            else:
                await ctx.send(f'The verification role is {role.mention}.', ephemeral=True)
        else:
            await self.verification_settings_store.set_verification_role_id(guild_id=ctx.guild.id, role_id=role.id)
            await ctx.send(f'The verification request channel has been set to {role.mention}.', ephemeral=True)


class MissingWelcomeMessageError(Exception):
    """Raised when the welcome message for a particular verification request is missing."""
    pass


class VerificationRequestView(ui.View):
    """A button that allows a user to request verification."""

    def __init__(self, verification_system: VerificationSystem) -> None:
        super().__init__(timeout=None)
        self.vs = verification_system

    async def interaction_check(self, interaction: Interaction) -> bool:
        mention_pattern = re.compile('<@!?([0-9]+)>')
        embed_description = interaction.message.embeds[0].description
        mentioned_user_ids = mention_pattern.findall(embed_description)
        mentioned_user_ids = [int(x) for x in mentioned_user_ids]
        if interaction.user.id not in mentioned_user_ids:
            _logger.info(f"{tools.user_string(interaction.user)} clicked someone else's verification button.")
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
        _logger.info(f'{tools.user_string(interaction.user)} clicked their own verification button. '
                     f'Sending basic info view.')
        choose_basic_info_view = ChooseBasicInfoView(verification_system=self.vs)
        await interaction.response.send_message(view=choose_basic_info_view, ephemeral=True)


class ChooseBasicInfoView(ui.View):
    """Asks the user about their age and gender."""

    def __init__(self, verification_system: VerificationSystem) -> None:
        super().__init__(timeout=None)
        self.vs = verification_system
        # Thirteen is the minimum age Discord allows.
        self.age_ranges = ('13', '14', '15', '16', '17', '18', '19', '20-24', '25-29', '30-39', '40-49', '50-59', '60+')
        self.age_range_select = ui.Select(
            placeholder="What's your age-range?",
            options=[SelectOption(label=label) for label in self.age_ranges],
            custom_id='select_age_range'
        )
        self.age_range_select.callback = self.age_range_selected
        self.add_item(self.age_range_select)

        self.genders = ('male', 'female', 'non-binary')
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
        age_range = self.age_range_select.values
        age_range = age_range and age_range[0]
        _logger.info(f'{tools.user_string(interaction.user)} selected {age_range=}.')
        await interaction.response.defer()

    async def gender_selected(self, interaction: Interaction):
        gender = self.gender_select.values
        gender = gender and gender[0]
        _logger.info(f'{tools.user_string(interaction.user)} selected {gender=}.')
        await interaction.response.defer()

    async def submit(self, interaction: Interaction) -> None:
        # Get the join message. First, look if it is available in cache, otherwise, fetch it.
        if interaction.message.reference is not None:
            if interaction.message.reference.cached_message is None:
                channel = self.vs.bot.get_channel(interaction.message.reference.channel_id)
                join_message = await channel.fetch_message(interaction.message.reference.message_id)
            else:
                join_message = interaction.message.reference.cached_message
        else:
            raise MissingWelcomeMessageError()

        age_range = self.age_range_select.values
        age_range = age_range and age_range[0]
        gender = self.gender_select.values
        gender = gender and gender[0]

        _logger.info(f'{tools.user_string(interaction.user)} submitted the basic info {age_range=} and {gender=}.')

        if not gender or not age_range:
            await interaction.response.send_message(content='Please fill out both fields!', ephemeral=True)

        assert age_range in self.age_ranges
        assert gender in self.genders
        choose_advanced_info_modal = ChooseAdvancedInfoModal(verification_system=self.vs, age_range=age_range,
                                                             gender=gender, welcome_message=join_message)
        await interaction.response.send_modal(choose_advanced_info_modal)
        await interaction.edit_original_response(content='To retry, click the `Verify me!` button again.', view=None)


class ChooseAdvancedInfoModal(ui.Modal, title='Just a few more questions...'):
    """Asks the user about their reason for joining."""

    def __init__(self, verification_system: VerificationSystem, age_range: str, gender: str,
                 welcome_message: Message) -> None:
        super().__init__()

        self.vs = verification_system
        self.age_range = age_range
        self.gender = gender
        self.welcome_message = welcome_message

        self.referrer_text_input = ui.TextInput(
            label='Referrer',
            placeholder='How did you find out about this server?',
            required=True,
            max_length=100
        )
        self.join_reason_text_input = ui.TextInput(
            label='Join Reason',
            placeholder='Why are you here? Please give a detailed description.',
            style=discord.TextStyle.paragraph,
            required=True,
            min_length=50,
            max_length=500
        )

        self.add_item(self.referrer_text_input)
        self.add_item(self.join_reason_text_input)

    async def on_submit(self, interaction: Interaction) -> None:
        _logger.info(f'{tools.user_string(interaction.user)} submitted their verification request with '
                     f'{self.age_range=}, {self.gender=}, {self.referrer_text_input.value=} and '
                     f'{self.join_reason_text_input.value=}.')

        # Get the verification channel.
        request_channel_id = await self.vs.verification_settings_store.get_request_channel_id(interaction.guild_id)
        request_channel = interaction.guild.get_channel(request_channel_id)

        # Open a new user verification request in the database.
        verification_request = await self.vs.verification_request_store.create(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
            join_channel_id=self.welcome_message.channel.id,
            join_message_id=self.welcome_message.id,
        )

        # Create the verification notification embed.
        description = f'User {interaction.user.mention} wants to be verified. They provided the following information.'
        embed = Embed(title='Verification Request', description=description, color=discord.Color.blue(),
                      timestamp=datetime.now(timezone.utc))
        embed.add_field(name='age-range', value=self.age_range)
        embed.add_field(name='gender', value=self.gender)
        embed.add_field(name='referrer', value=self.referrer_text_input.value)
        embed.add_field(name='join reason', value=self.join_reason_text_input.value)
        embed.set_author(name=tools.user_string(interaction.user),
                         url=f'https://discordapp.com/users/{interaction.user.id}',
                         icon_url=interaction.user.display_avatar)
        file = discord.File(self.vs.bot.config.img_dir / 'accept_reject.png', filename='image.png')
        embed.set_thumbnail(url='attachment://image.png')

        # Create the verification notification view.
        verification_notification_view = VerificationNotificationView(verification_system=self.vs,
                                                                      verification_request=verification_request)

        # Send the embed and view to the verification request channel.
        await request_channel.send(embed=embed, file=file, view=verification_notification_view)

        # Edit the original verification request button to show that verification is pending.
        view = VerificationRequestView(verification_system=self.vs)
        button = view.children[0]
        button.disabled = True
        button.label = 'Verification pending ...'
        await self.welcome_message.edit(view=view)

        # Let the user know that the staff has been notified.
        await interaction.response.send_message(
            f'Thanks for your response, {interaction.user.mention}! The staff has been notified.',
            ephemeral=True,
        )


class VerificationNotificationView(ui.View):
    """Notifies the staff about a new ticket request and lets them accept or reject it.
    In the first case, creates a new channel. In both cases, notifies the user about the staff decision."""

    def __init__(self, verification_system: VerificationSystem, verification_request: VerificationRequest) -> None:
        super().__init__(timeout=None)
        self.vs = verification_system
        self.verification_request = verification_request
        self.lock = asyncio.Lock()
        self.message: Optional[Message] = None
        self.accept_button = ui.Button(label='Accept', style=ButtonStyle.green, emoji=emojize(':check_mark_button:'),
                                       custom_id=f'accept_verification_request#{self.verification_request.id}')
        self.reject_button = ui.Button(label='Reject', style=ButtonStyle.blurple, emoji=emojize(':no_entry:'),
                                       custom_id=f'reject_verification_request#{self.verification_request.id}')
        self.accept_button.callback = self.accept_verification_request
        self.reject_button.callback = self.reject_verification_request
        self.add_item(self.accept_button)
        self.add_item(self.reject_button)

    async def interaction_check(self, interaction: Interaction) -> bool:
        # INFO: Even though `reject_verification_request` kicks members, kick permissions are not necessary.
        # The rationale is that this only applies to new members.
        if interaction.user.guild_permissions.manage_roles:
            return True
        else:
            member = interaction.guild.get_member(self.verification_request.user_id)
            _logger.info(
                f"{tools.user_string(interaction.user)} tried to verify or reject {tools.user_string(member)}'s "
                "verification request even though they lack the necessary permissions."
            )
            await interaction.response.send_message('You are not allowed to do this action!', ephemeral=True)
            return False

    async def accept_verification_request(self, interaction: Interaction) -> None:
        # The lock and `is_finished()` call ensure that the view is only responded to once.
        async with self.lock:
            if self.is_finished():
                return

            # Retrieve the member this verification request belongs to.
            member = interaction.guild.get_member(self.verification_request.user_id)
            if member is None:
                user = self.vs.bot.get_user(self.verification_request.user_id)
                user_mention = user.mention if user is not None else '<deleted user>'
                msg = f"{interaction.user.mention} tried to accept {user_mention}'s verification request but it " \
                      "appears they already left."
                _logger.info(msg)
                await interaction.response.send_message(msg)
            else:
                _logger.info(f"{tools.user_string(interaction.user)} accepted {tools.user_string(member)}'s "
                             "verification request.")

                # Assign the verification role to the user.
                # TODO Assign the other roles (gender and age-range).
                role_id = await self.vs.verification_settings_store.get_verification_role_id(interaction.guild_id)
                role = interaction.guild.get_role(role_id)
                try:
                    await member.add_roles(role, reason='verify the user')
                except discord.errors.Forbidden:
                    _logger.exception('The bot role is probably below the verification role.')
                    interaction.response.send_message(
                        'Error: Lacking permissions. The bot role is probably below the verification role.',
                        ephemeral=True
                    )
                    return

                # Store the decision to verify the user in the database.
                await self.vs.verification_request_store.close(self.verification_request, True)

                # Welcome the user with additional information.
                welcome_channel_id = await self.vs.verification_settings_store.get_welcome_channel_id(
                    interaction.guild_id
                )
                welcome_channel = interaction.guild.get_channel(welcome_channel_id)
                welcome_message = await self.vs.verification_settings_store.get_welcome_message(
                    interaction.guild_id
                )
                description = welcome_message.replace('<user>', member.mention)
                # embed = Embed(title=f'Welcome to {interaction.guild.name}!',
                #               description=description,
                #               color=discord.Color.green(),
                #               timestamp=datetime.now(timezone.utc))
                # embed.set_author(name=tools.user_string(interaction.user),
                #                  url=f'https://discordapp.com/users/{interaction.user.id}',
                #                  icon_url=interaction.user.display_avatar)
                # file = discord.File(self.vs.bot.img_dir / 'welcome2.png', filename='image.png')
                # embed.set_thumbnail(url='attachment://image.png')
                await welcome_channel.send(content=description)

            # Remove the welcome message from the join channel. At this point, if it does not exist, we do not care.
            join_channel_id = self.verification_request.join_channel_id
            join_channel = self.vs.bot.get_channel(join_channel_id)
            join_message = await join_channel.fetch_message(self.verification_request.join_message_id)
            if join_message is not None:
                await join_message.delete()

            # Stop listening to the view and deactivate it.
            self.stop()
            self.remove_item(self.reject_button)
            self.accept_button.label = f'{self.accept_button.label}ed'
            self.accept_button.disabled = True

            # Edit the original verification notification embed.
            embed = interaction.message.embeds[0]
            embed.title += ' [ACCEPTED]'
            embed.colour = discord.Color.green()
            file = discord.File(self.vs.bot.config.img_dir / 'accepted_verification_request.png', filename='image.png')
            embed.set_thumbnail(url='attachment://image.png')

            # Send the edited embed and view.
            await interaction.response.edit_message(embed=embed, attachments=[file], view=self)
            await interaction.followup.send(
                f"{interaction.user.mention} accepted {member.mention}'s verification request!"
            )

    async def reject_verification_request(self, interaction: Interaction) -> None:
        # The lock and `is_finished()` call ensure that the view is only responded to once.
        async with self.lock:
            if self.is_finished():
                return

            # Retrieve the member this verification request belongs to.
            member = interaction.guild.get_member(self.verification_request.user_id)
            if member is None:
                user = self.vs.bot.get_user(self.verification_request.user_id)
                user_mention = user.mention if user is not None else '<deleted user>'
                msg = f"{interaction.user.mention} clicked the `Reject` button for {user_mention}'s verification " \
                      "request but it appears they already left."
                _logger.info(msg)
                await interaction.response.send_message(msg)
            else:
                _logger.info(f"{tools.user_string(interaction.user)} clicked the `Reject` button for "
                             f"{tools.user_string(member)}'s verification request.")

                self.message = interaction.message

                # Ask for confirmation and a reason to kick the user.
                confirm_kick_modal = ConfirmKickModal(verification_system=self.vs,
                                                      verification_request=self.verification_request,
                                                      verification_notification_view=self)
                await interaction.response.send_modal(confirm_kick_modal)


class ConfirmKickModal(ui.Modal, title='Kick the user?'):
    """Asks the staff member to confirm if they want to reject the verification request and kick the user."""

    def __init__(self, verification_system: VerificationSystem, verification_request: VerificationRequest,
                 verification_notification_view: VerificationNotificationView) -> None:
        super().__init__()
        self.vs = verification_system
        self.verification_request = verification_request
        self.verification_notification_view = verification_notification_view
        self.kick_reason_text_input = ui.TextInput(
            label='Kick Reason',
            placeholder='Describe why the user cannot be verified and will be kicked.',
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=500
        )
        self.add_item(self.kick_reason_text_input)

    async def on_submit(self, interaction: Interaction) -> None:
        # Kick the user.
        user_id = self.verification_request.user_id
        member = interaction.guild.get_member(user_id)
        kick_reason = self.kick_reason_text_input.value
        if member is None:
            user = self.vs.bot.get_user(self.verification_request.user_id)
            user_mention = user.mention if user is not None else '<deleted user>'
            msg = f"{interaction.user.mention} tried to reject {user_mention}'s verification request and kick them " \
                  f"with {kick_reason=} but it appears they already left."
            _logger.info(msg)
            await interaction.response.send_message(msg)
        else:
            _logger.info(f"{tools.user_string(interaction.user)} rejected {tools.user_string(member)}'s verification "
                         f"request for {kick_reason=}.")
            await member.kick(reason=kick_reason)

            # Store the decision to not verify the user in the database.
            await self.vs.verification_request_store.close(self.verification_request, False)

            # Remove the join message from the join channel. At this point, if it does not exist, we do not care.
            join_channel_id = await self.vs.verification_settings_store.get_join_channel_id(
                guild_id=interaction.guild_id)
            join_channel = self.vs.bot.get_channel(join_channel_id)
            if join_channel is not None:
                join_message = await join_channel.fetch_message(self.verification_request.join_message_id)
                if join_message is not None:
                    await join_message.delete()

        # Modify verification notification message.
        # The lock and `is_finished()` call ensure that the view is only responded to once.
        async with self.verification_notification_view.lock:
            if self.is_finished():
                return

            # Stop listening to the view and deactivate it.
            self.stop()
            self.verification_notification_view.remove_item(self.verification_notification_view.accept_button)
            reject_button_label = self.verification_notification_view.reject_button.label
            self.verification_notification_view.reject_button.label = f'{reject_button_label}ed'
            self.verification_notification_view.reject_button.disabled = True

            # Edit the original verification notification embed.
            embed = self.verification_notification_view.message.embeds[0]
            embed.title += ' [REJECTED]'
            embed.colour = discord.Color.red()
            file = discord.File(self.vs.bot.config.img_dir / 'rejected_verification_request.png', filename='image.png')
            embed.set_thumbnail(url='attachment://image.png')

            # Send the edited embed and view.
            await self.verification_notification_view.message.edit(embed=embed,
                                                                   attachments=[file],
                                                                   view=self.verification_notification_view)
            message = f"{interaction.user.mention} rejected {member.mention}'s verification request! " \
                      "They were subsequently kicked."
            if kick_reason:
                message += f' They have provided the following reason:\n{tools.quote_message(kick_reason)}' or ''
            await interaction.response.send_message(message)


async def setup(bot: SlimBot) -> None:
    await bot.add_cog(VerificationSystem(bot))
