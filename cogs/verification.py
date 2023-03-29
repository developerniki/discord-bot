import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import ui, TextChannel, Member, ButtonStyle, Interaction, Role, SelectOption, Message, Embed, User, Guild, \
    Forbidden
from discord.ext import commands, tasks
from emoji import emojize

from database import VerificationRequest, VerificationSettingsStore, VerificationRequestStore, \
    ActiveVerificationMessageStore, ActiveVerificationMessage, VerificationRuleMessageStore, VerificationRuleMessage
from slimbot import SlimBot, tools

_logger = logging.getLogger(__name__)

# TODO Refactor.
NUM_VERIFICATION_REMINDERS_BEFORE_KICK = 4
REMIND_TO_VERIFY_EVERY_N_SECS = 8 * 3600
N_SECS_BETWEEN_VERIFICATION_REMINDERS = 60


class VerificationSystem(commands.Cog, name='Verification System'):
    """Asks new members to verify, notifies staff, assigns a verification role, and welcomes the member."""

    def __init__(self, bot: SlimBot) -> None:
        self.bot = bot
        self._views_added = False

        self.verification_settings_store = VerificationSettingsStore(self.bot.config.db_file)
        self.verification_request_store = VerificationRequestStore(self.bot.config.db_file)
        self.active_ver_msg_store = ActiveVerificationMessageStore(self.bot.config.db_file)
        self.rule_msg_store = VerificationRuleMessageStore(self.bot.config.db_file)
        self._views_added = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self.bot.wait_until_ready()

        if not self._views_added:
            verification_request_view = VerificationRequestView(self)
            self.bot.add_view(verification_request_view)

            choose_basic_info_view = ChooseBasicInfoView(self)
            self.bot.add_view(choose_basic_info_view)

            pending_verification_requests = await self.verification_request_store.get_pending_verification_requests()
            for verification_request in pending_verification_requests:
                verification_request_view = VerificationNotificationView(
                    verification_system=self,
                    verification_request=verification_request
                )
                self.bot.add_view(verification_request_view)

            self._views_added = True

        # Start task loops.
        async def task():
            await asyncio.sleep(REMIND_TO_VERIFY_EVERY_N_SECS)
            self.give_button_to_unverified_users_without_active_verification_request.start()

        asyncio.create_task(task())

    async def member_is_verified(self, guild: Guild, member: Member) -> bool:
        verified = False
        for role in member.roles:
            if role.id == await self.verification_settings_store.get_verification_role_id(guild.id):
                verified = True
                break
        return verified

    @tasks.loop(seconds=REMIND_TO_VERIFY_EVERY_N_SECS)
    async def give_button_to_unverified_users_without_active_verification_request(self) -> None:
        _logger.info('Giving buttons to unverified users')

        verification_requests = await self.verification_request_store.get_pending_verification_requests()
        user_ids_with_active_requests = {request.user_id for request in verification_requests}

        unverified_members = []
        for guild in self.bot.guilds:
            for member in guild.members:
                has_active_request = member.id in user_ids_with_active_requests
                if not member.bot and not await self.member_is_verified(guild, member) and not has_active_request:
                    unverified_members.append(member)

        random.shuffle(unverified_members)

        for member in unverified_members:
            has_active_request = member.id in user_ids_with_active_requests
            # In case member verified / requested verification in the meantime, the member won't receive another button.
            if not await self.member_is_verified(member.guild, member) and not has_active_request:
                num_reminders = await self.active_ver_msg_store.get_num_active_verification_messages_by_user(
                    guild_id=member.guild.id, user_id=member.id
                )
                # If the user received 0 verification reminders, use the rule acceptance reminders to determine whether the user should be kicked.
                if num_reminders == 0:
                    num_reminders = await self.rule_msg_store.get_num_rule_messages_by_user(
                        guild_id=member.guild.id, user_id=member.id
                    )
                _logger.info(
                    f'{tools.user_string(member)} has received {num_reminders}/{NUM_VERIFICATION_REMINDERS_BEFORE_KICK} reminders.')
                if num_reminders > NUM_VERIFICATION_REMINDERS_BEFORE_KICK:
                    try:
                        await member.kick(reason='user did not verify')
                        _logger.info(f'Kicked {tools.user_string(member)} because they did not verify')
                    except Forbidden:
                        _logger.warning(f'Could not kick {tools.user_string(member)} in guild with id '
                                        f'{member.guild.id} because permissions are missing')
                else:
                    if member.pending:
                        await self._create_rule_acceptance_message(member)
                    else:
                        await self._create_verification_message(member)
            # TODO Make this timer guild dependent.
            await asyncio.sleep(N_SECS_BETWEEN_VERIFICATION_REMINDERS)

    async def _create_verification_message(self, user: User | Member) -> bool:
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
            _logger.warning(f'One of the necessary settings is not configured/not configured properly for the '
                            f'verification system to work properly in guild with id {user.guild.id} and name '
                            f'{user.guild.name}.')
            success = False
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
            embed.set_author(name=tools.user_string(user),
                             url=f'https://discordapp.com/users/{user.id}',
                             icon_url=user.display_avatar)
            file = discord.File(self.bot.config.img_dir / 'welcome1.png', filename='image.png')
            embed.set_thumbnail(url='attachment://image.png')
            message = await join_channel.send(embed=embed, file=file, view=verification_request_view)
            await self.active_ver_msg_store.create_active_verification_message(
                message_id=message.id, guild_id=user.guild.id, user_id=user.id, channel_id=join_channel.id
            )
            success = True
        return success

    async def _remove_active_verification_messages(self, guild: Guild, user: User | Member) -> None:
        messages = await self.active_ver_msg_store.get_active_verification_messages_by_user(
            guild_id=guild.id, user_id=user.id
        )
        for message_ in messages:
            message_: ActiveVerificationMessage
            channel = self.bot.get_channel(message_.channel_id)
            try:
                message = await channel.fetch_message(message_.id)
                await message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                _logger.error(
                    f'Could not delete active verification message with {guild.id=}, {user.id=} and {message_.id=} '
                    f'and got error {e}.'
                )
        await self.active_ver_msg_store.delete_active_verification_messages_by_user(guild_id=guild.id, user_id=user.id)

    async def _create_rule_acceptance_message(self, user: User | Member) -> None:
        join_channel_id = await self.verification_settings_store.get_join_channel_id(user.guild.id)
        join_channel = join_channel_id and user.guild.get_channel(join_channel_id)
        if join_channel:
            message = await join_channel.send(
                f'Welcome, {user.mention}! Please accept the rules to get a verification button.'
            )
            await self.rule_msg_store.create_rule_message(
                message_id=message.id, guild_id=user.guild.id, user_id=user.id, channel_id=join_channel.id
            )

    async def _remove_rule_acceptance_messages(self, guild: Guild, user: User | Member) -> None:
        messages = await self.rule_msg_store.get_rule_messages_by_user(guild_id=guild.id, user_id=user.id)
        for message_ in messages:
            message_: VerificationRuleMessage
            channel = self.bot.get_channel(message_.channel_id)
            try:
                message = await channel.fetch_message(message_.id)
                await message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                _logger.error(
                    f'Could not delete rule message with {guild.id=}, {user.id=} and {message_.id=} and got error {e}.'
                )
        await self.rule_msg_store.delete_rule_messages_by_user(guild_id=guild.id, user_id=user.id)

    @commands.Cog.listener()
    async def on_member_join(self, member: Member) -> None:
        _logger.info(f'{tools.user_string(member)} joined the server!')
        if not member.bot:
            # To be safe, remove the active verification messages
            # (so the user is not accidentally kicked by reaching the threshold).
            await self._remove_active_verification_messages(guild=member.guild, user=member)
            if not member.pending:
                await self._create_verification_message(member)
            else:
                # Tell the member to accept the rules by sending a message in the join channel.
                join_channel_id = await self.verification_settings_store.get_join_channel_id(member.guild.id)
                join_channel = join_channel_id and member.guild.get_channel(join_channel_id)
                if join_channel:
                    await self._create_rule_acceptance_message(member)

    @commands.Cog.listener()
    async def on_member_update(self, before: Member, after: Member) -> None:
        if before.pending and not after.pending:
            _logger.info(f'{tools.user_string(after)} completed the rules screening!')
            if after.bot:
                _logger.info(f'{tools.user_string(after)} is a bot, so not making a verification button.')
            else:
                await self._remove_rule_acceptance_messages(guild=after.guild, user=after)
                await self._create_verification_message(after)

    @commands.Cog.listener()
    async def on_member_remove(self, member: Member) -> None:
        _logger.info(f'{tools.user_string(member)} left the server!')
        await self._remove_active_verification_messages(guild=member.guild, user=member)
        await self._remove_rule_acceptance_messages(guild=member.guild, user=member)
        pending_requests = await self.verification_request_store.get_pending_verification_requests_by_user(
            guild_id=member.guild.id, user_id=member.id
        )
        for verification_request in pending_requests:
            verification_request: VerificationRequest
            channel_id = verification_request.notification_channel_id
            if channel_id:
                channel = member.guild.get_channel(channel_id)
                if channel:
                    try:
                        message = await channel.fetch_message(verification_request.notification_message_id)
                        # Edit the original verification notification embed.
                        embed = message.embeds[0]
                        embed.title += ' [USER LEFT]'
                        embed.colour = discord.Color.darker_gray()
                        file = discord.File(self.bot.config.img_dir / 'user_left.png', filename='image.png')
                        embed.set_thumbnail(url='attachment://image.png')
                        # Edit the original verification notification view.
                        view = discord.ui.View.from_message(message)
                        # Delete all the buttons.
                        for button in view.children:
                            if isinstance(button, discord.ui.Button):
                                view.remove_item(button)
                        # Update the message with the new embed and view.
                        message: discord.Message
                        await message.edit(embed=embed, attachments=[file], view=view)
                        _logger.info(f'Edited the verification notification embed for {tools.user_string(member)} and '
                                     f'sent it.')
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                        _logger.exception(
                            f'Could not fetch verification request notification message with {member.guild.id=}, '
                            f'{member.id=} and {verification_request.notification_message_id=}.'
                        )
            await self.verification_request_store.close_verification_request(verification_request=verification_request,
                                                                             verified=False)

    @commands.hybrid_group()
    @commands.has_guild_permissions(manage_roles=True, manage_channels=True)
    async def verification(self, ctx):
        pass

    @verification.command()
    @commands.has_guild_permissions(manage_channels=True)
    async def button(self, ctx: commands.Context, user: User):
        """Create a verification button for `user`."""
        success = await self._create_verification_message(user)
        if not success:
            await ctx.send('Cannot create a button. First, configure the necessary settings using the '
                           '`/verification setup` command.', ephemeral=True)
        else:
            join_channel_id = await self.verification_settings_store.get_join_channel_id(ctx.guild.id)
            join_channel = join_channel_id and ctx.guild.get_channel(join_channel_id)
            await ctx.send(f'Created a verification button at {join_channel.mention}.', ephemeral=True)

    @verification.command()
    @commands.has_guild_permissions(manage_channels=True)
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
        await ctx.send('Everything set up for the verification system to work! You might also want to set the adult '
                       'role using the `/adultrole` command.', ephemeral=True)

    @verification.command()
    @commands.has_guild_permissions(manage_channels=True)
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
    @commands.has_guild_permissions(manage_channels=True)
    async def joinmessage(self, ctx: commands.Context, *, message: Optional[str]) -> None:
        """Get or set the join message, depending on whether `message` is present."""
        if message is None:
            message = await self.verification_settings_store.get_join_message(ctx.guild.id)
            if message is None:
                await ctx.send(f'The join message is not configured yet.', ephemeral=True)
            else:
                await ctx.send(f'The join message is `{message}`.', ephemeral=True)
        else:
            await self.verification_settings_store.set_join_message(guild_id=ctx.guild.id, message=message)
            await ctx.send(f'The join message has been set to `{message}`.', ephemeral=True)

    @verification.command()
    @commands.has_guild_permissions(manage_channels=True)
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
    @commands.has_guild_permissions(manage_channels=True)
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
    @commands.has_guild_permissions(manage_channels=True)
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
    @commands.has_guild_permissions(manage_channels=True)
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
            await ctx.send(f'The verification role has been set to {role.mention}.', ephemeral=True)

    @verification.command()
    @commands.has_guild_permissions(manage_channels=True)
    async def adultrole(self, ctx: commands.Context, role: Optional[Role]) -> None:
        """Get or set the adult role, depending on whether `role` is present."""
        if role is None:
            role_id = await self.verification_settings_store.get_adult_role_id(ctx.guild.id)
            role = role_id and ctx.guild.get_role(role_id)
            if role is None:
                await ctx.send(f'The adult role is not configured yet.', ephemeral=True)
            else:
                await ctx.send(f'The adult role is {role.mention}.', ephemeral=True)
        else:
            await self.verification_settings_store.set_adult_role_id(guild_id=ctx.guild.id, role_id=role.id)
            await ctx.send(f'The adult role has been set to {role.mention}.', ephemeral=True)


class MissingWelcomeMessageError(Exception):
    """Raised when the welcome message for a particular verification request is missing."""
    pass


class VerificationRequestView(ui.View):
    """A button that allows a user to request verification."""
    mention_pattern = re.compile('<@!?([0-9]+)>')

    def __init__(self, verification_system: VerificationSystem) -> None:
        super().__init__(timeout=None)
        self.vs = verification_system

    async def interaction_check(self, interaction: Interaction) -> bool:
        embed_description = interaction.message.embeds[0].description
        mentioned_user_ids = self.mention_pattern.findall(embed_description)
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
        # Thirteen is the minimum age Discord allows. Because this age is parsed later, do not change the format when
        # adding or removing values!
        self.age_ranges = ('13', '14', '15', '16', '17', '18', '19', '20-24', '25-29', '30-39', '40-49', '50-59', '60+')
        self.age_range_select = ui.Select(
            placeholder="What's your age?",
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
        else:
            assert age_range in self.age_ranges
            assert gender in self.genders
            choose_advanced_info_modal = ChooseAdvancedInfoModal(verification_system=self.vs, age_range=age_range,
                                                                 gender=gender, welcome_message=join_message)
            await interaction.response.send_modal(choose_advanced_info_modal)
            await interaction.edit_original_response(content='To retry, click the `Verify me!` button again.',
                                                     view=None)


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
            min_length=35,
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
        verification_request = await self.vs.verification_request_store.create_verification_request(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
            join_channel_id=self.welcome_message.channel.id,
            join_message_id=self.welcome_message.id,
            age=self.age_range,
            gender=self.gender
        )

        # Create the verification notification embed.
        description = f'User {interaction.user.mention} wants to be verified. They provided the following information.'
        embed = Embed(title='Verification Request', description=description, color=discord.Color.blue(),
                      timestamp=datetime.now(timezone.utc))
        embed.add_field(name='age', value=self.age_range)
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
        message = await request_channel.send(embed=embed, file=file, view=verification_notification_view)

        # Update the verification request with the channel and message id.
        await self.vs.verification_request_store.set_notification_channel_and_message(
            verification_request=verification_request,
            notification_channel_id=message.channel.id,
            notification_message_id=message.id
        )

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

            await interaction.response.defer()  # In case we take longer than 3 seconds.

            # Retrieve the member this verification request belongs to.
            member = interaction.guild.get_member(self.verification_request.user_id)
            if member is None:
                user = self.vs.bot.get_user(self.verification_request.user_id)
                user_mention = user.mention if user is not None else '<deleted user>'
                msg = f"{interaction.user.mention} tried to accept {user_mention}'s verification request but it " \
                      "appears they already left."
                _logger.info(msg)
                await interaction.response.send_message(msg)
                return
            else:
                _logger.info(f"{tools.user_string(interaction.user)} accepted {tools.user_string(member)}'s "
                             "verification request.")

                # Assign the verification and adult (if eligible) roles to the user.
                role_id = await self.vs.verification_settings_store.get_verification_role_id(interaction.guild_id)
                role = interaction.guild.get_role(role_id)
                try:
                    await member.add_roles(role, reason='verify the user')
                    _logger.info(f'Assigned {role.name} to {tools.user_string(member)}.')
                except discord.errors.Forbidden:
                    _logger.exception('The bot role is probably below the verification role.')
                    interaction.response.send_message(
                        'Error: Lacking permissions. The bot role is probably below the verification role.',
                        ephemeral=True
                    )
                    return

                min_age = self.verification_request.age.replace('+', '')
                min_age = re.match(r'(?P<min_age>\d+)(?P<max_age>-\d+)?', min_age).group('min_age')
                min_age = int(min_age)
                if min_age >= 18:
                    adult_role_id = await self.vs.verification_settings_store.get_adult_role_id(interaction.guild_id)
                    adult_role = interaction.guild.get_role(adult_role_id)
                    if adult_role is not None:
                        await member.add_roles(adult_role, reason=f'verify the user, assigning adult role as age is at '
                                                                  f'least {min_age}')
                        _logger.info(f'Assigned {adult_role.name} to {tools.user_string(member)}.')

                # Store the decision to verify the user in the database.
                await self.vs.verification_request_store.close_verification_request(self.verification_request, True)

                # Welcome the user with additional information.
                welcome_channel_id = await self.vs.verification_settings_store.get_welcome_channel_id(
                    interaction.guild_id
                )
                welcome_channel = interaction.guild.get_channel(welcome_channel_id)
                welcome_message = await self.vs.verification_settings_store.get_welcome_message(interaction.guild_id)
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

            # Remove all welcome messages.
            _logger.info(f'Removing all welcome messages for {tools.user_string(member)}...')
            await self.vs._remove_active_verification_messages(guild=interaction.guild, user=member)
            _logger.info(f'Removed all welcome messages for {tools.user_string(member)}.')

            # Modify the buttons to indicate that the action has been taken.
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
            try:
                await interaction.response.send_message(
                    f"{interaction.user.mention} accepted {member.mention}'s verification request!"
                )
                await interaction.message.edit(embed=embed, attachments=[file], view=self)
                _logger.info(f'Edited the verification notification embed for {tools.user_string(member)} and sent it.')
            except discord.errors.NotFound:
                _logger.error(
                    f'The verification notification message with ID {interaction.id} (guild ID {interaction.guild.id},'
                    f'channel ID {interaction.channel.id}) could not be found, maybe because it was deleted.'
                )

            # Stop listening to this view.
            self.stop()

    async def reject_verification_request(self, interaction: Interaction) -> None:
        # The lock and `is_finished()` call ensure that the view is only responded to once.
        async with self.lock:
            if self.is_finished():
                return

            await interaction.response.defer()  # In case we take longer than 3 seconds.

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

                # Ask for confirmation and a reason to kick the user.
                confirm_kick_modal = ConfirmKickModal(verification_system=self.vs,
                                                      verification_request=self.verification_request,
                                                      verification_notification_view=self,
                                                      message=interaction.message)
                await interaction.response.send_modal(confirm_kick_modal)


class ConfirmKickModal(ui.Modal, title='Kick the user?'):
    """Asks the staff member to confirm if they want to reject the verification request and kick the user."""

    def __init__(self, verification_system: VerificationSystem, verification_request: VerificationRequest,
                 verification_notification_view: VerificationNotificationView, message: Message) -> None:
        super().__init__()
        self.vs = verification_system
        self.verification_request = verification_request
        self.verification_notification_view = verification_notification_view
        self.notification_verification_view_message = message
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
            try:
                await member.kick(reason=kick_reason)
            except Forbidden:
                _logger.warning(f"Couldn't kick {tools.user_string(member)}")

            # Store the decision to not verify the user in the database.
            await self.vs.verification_request_store.close_verification_request(self.verification_request, False)

            # Remove the join message from the join channel. At this point, if it does not exist, we do not care.
            join_channel_id = await self.vs.verification_settings_store.get_join_channel_id(
                guild_id=interaction.guild_id)
            join_channel = self.vs.bot.get_channel(join_channel_id)
            if join_channel is not None:
                try:
                    join_message = await join_channel.fetch_message(self.verification_request.join_message_id)
                    if join_message is not None:
                        await join_message.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass

            # Remove other welcome messages.
            await self.vs._remove_active_verification_messages(guild=interaction.guild, user=member)

        # Modify verification notification message.
        # The lock and `is_finished()` call ensure that the view is only responded to once.
        async with self.verification_notification_view.lock:
            if self.is_finished():
                return

            # Modify the buttons to indicate that the action has been taken.
            self.verification_notification_view.remove_item(self.verification_notification_view.accept_button)
            reject_button_label = self.verification_notification_view.reject_button.label
            self.verification_notification_view.reject_button.label = f'{reject_button_label}ed'
            self.verification_notification_view.reject_button.disabled = True

            # Edit the original verification notification embed.
            embed = self.notification_verification_view_message.embeds[0]
            embed.title += ' [REJECTED]'
            embed.colour = discord.Color.red()
            file = discord.File(self.vs.bot.config.img_dir / 'rejected_verification_request.png', filename='image.png')
            embed.set_thumbnail(url='attachment://image.png')

            # Send the edited embed and view.
            try:
                message = f"{interaction.user.mention} rejected {member.mention}'s verification request! " \
                          "They were subsequently kicked."
                if kick_reason:
                    message += f' They have provided the following reason:\n{tools.quote_message(kick_reason)}' or ''
                await interaction.response.send_message(message)
                await self.notification_verification_view_message.edit(
                    embed=embed,
                    attachments=[file],
                    view=self.verification_notification_view
                )
            except discord.errors.NotFound:
                _logger.error(
                    f'The verification notification message with ID {interaction.id} (guild ID {interaction.guild.id},'
                    f'channel ID {interaction.channel.id}) could not be found, maybe because it was deleted.'
                )

            # Stop listening to this view.
            self.stop()


async def setup(bot: SlimBot) -> None:
    await bot.add_cog(VerificationSystem(bot))
