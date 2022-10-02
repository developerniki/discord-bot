import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional, List

import aiosqlite
import discord
from discord import ui, TextChannel, Member, ButtonStyle, Interaction, Role, SelectOption, Message, Embed, User
from discord.ext import commands
from emoji import emojize

import tools
from main import SlimBot, BaseStore

_logger = logging.getLogger(__name__)


class VerificationSystem(commands.GroupCog, name='verify'):
    """A group cog that verifies new members on join and then welcomes them."""

    def __init__(self, bot: SlimBot) -> None:
        self.bot = bot
        self._views_added = False

        self.verification_settings_store = VerificationSettingStore(self.bot.db_loc)
        self.verification_request_store = VerificationRequestStore(self.bot.db_loc)
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

    @commands.Cog.listener()
    async def on_member_join(self, member: Member) -> None:
        _logger.info(f'{tools.user_string(member)} joined the server!')
        welcome_channel_id = await self.verification_settings_store.get_welcome_channel_id(member.guild.id)
        welcome_channel = welcome_channel_id and member.guild.get_channel(welcome_channel_id)

        verified_welcome_channel_id = await self.verification_settings_store.get_welcome_channel_id(member.guild.id)
        verified_welcome_channel = welcome_channel_id and member.guild.get_channel(verified_welcome_channel_id)

        verified_welcome_message = await self.verification_settings_store.get_verified_welcome_message(member.guild.id)

        request_channel_id = await self.verification_settings_store.get_request_channel_id(member.guild.id)
        request_channel = request_channel_id and member.guild.get_channel(request_channel_id)

        role_id = await self.verification_settings_store.get_role_id(member.guild.id)
        role = role_id and member.guild.get_role(role_id)

        if None in (welcome_channel, verified_welcome_channel, verified_welcome_message, request_channel, role):
            _logger.warning('One of the necessary settings is not configured/not configured properly for the '
                            'verification system to work!')
            return
        else:
            _logger.info(f'Making a verification button for {tools.user_string(member)}.')
            verification_request_view = VerificationRequestView(self)
            description = f'Nice to have you, {member.mention}! To have access to the rest of the server, ' \
                          'please click on the button below and complete the verification process.'
            embed = Embed(title=f'Welcome to {member.guild.name}!', description=description,
                          color=discord.Color.blue(), timestamp=datetime.now(timezone.utc))
            file = discord.File(self.bot.img_dir / 'welcome1.png', filename='image.png')
            embed.set_thumbnail(url='attachment://image.png')
            await welcome_channel.send(embed=embed, file=file, view=verification_request_view)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_roles=True)
    async def verification_button(self, ctx: commands.Context, user: User):
        """Create a verification button for `user`."""
        welcome_channel_id = await self.verification_settings_store.get_welcome_channel_id(ctx.guild.id)
        welcome_channel = welcome_channel_id and ctx.guild.get_channel(welcome_channel_id)

        verified_welcome_channel_id = await self.verification_settings_store.get_welcome_channel_id(ctx.guild.id)
        verified_welcome_channel = welcome_channel_id and ctx.guild.get_channel(verified_welcome_channel_id)

        verified_welcome_message = await self.verification_settings_store.get_verified_welcome_message(ctx.guild.id)

        request_channel_id = await self.verification_settings_store.get_request_channel_id(ctx.guild.id)
        request_channel = request_channel_id and ctx.guild.get_channel(request_channel_id)

        role_id = await self.verification_settings_store.get_role_id(ctx.guild.id)
        role = role_id and ctx.guild.get_role(role_id)

        if None in (welcome_channel, verified_welcome_channel, verified_welcome_message, request_channel, role):
            await ctx.send(
                'Cannot create a button. First, configure the necessary settings using the '
                '`/setup_verification_system` command.',
                ephemeral=True
            )
        else:
            verification_request_view = VerificationRequestView(self)
            description = f'Nice to have you, {user.mention}! To have access to the rest of the server, ' \
                          'please click on the button below and complete the verification process.'
            embed = Embed(title=f'Welcome to {ctx.guild.name}!', description=description,
                          color=discord.Color.blue(), timestamp=datetime.now(timezone.utc))
            file = discord.File(self.bot.img_dir / 'welcome1.png', filename='image.png')
            embed.set_thumbnail(url='attachment://image.png')
            await ctx.send(embed=embed, file=file, view=verification_request_view)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def setup_verification_system(self, ctx: commands.Context,
                                        welcome_channel: TextChannel,
                                        verified_welcome_channel: TextChannel,
                                        verified_welcome_message: str,
                                        verification_request_channel: TextChannel,
                                        verification_role: Role) -> None:
        """Set up all necessary channels and roles for the verification system to work."""
        await self.verification_settings_store.set_welcome_channel_id(
            guild_id=ctx.guild.id,
            channel_id=welcome_channel.id
        )
        await self.verification_settings_store.set_verified_welcome_channel_id(
            guild_id=ctx.guild.id,
            channel_id=verified_welcome_channel.id
        )
        await self.verification_settings_store.set_verified_welcome_message(
            guild_id=ctx.guild.id,
            message=verified_welcome_message
        )
        await self.verification_settings_store.set_request_channel_id(
            guild_id=ctx.guild.id,
            channel_id=verification_request_channel.id
        )
        await self.verification_settings_store.set_role_id(
            guild_id=ctx.guild.id,
            role_id=verification_role.id
        )
        await ctx.send('Everything set up for the verification system to work!', ephemeral=True)

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
    async def get_verified_welcome_channel(self, ctx: commands.Context) -> None:
        """Get the verified welcome channel used to welcome the user with more information after verification."""
        channel_id = await self.verification_settings_store.get_verified_welcome_channel_id(ctx.guild.id)
        channel = channel_id and ctx.guild.get_channel(channel_id)
        if channel is None:
            await ctx.send(f'The verified welcome channel is not configured yet.', ephemeral=True)
        else:
            await ctx.send(f'The verified welcome channel is {channel.mention}.', ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def set_verified_welcome_channel(self, ctx: commands.Context, channel: TextChannel) -> None:
        """Set the verified welcome channel used to welcome the user with more information after verification."""
        await self.verification_settings_store.set_verified_welcome_channel_id(guild_id=ctx.guild.id,
                                                                               channel_id=channel.id)
        await ctx.send(f'The verified welcome channel has been set to {channel.mention}.', ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def get_verified_welcome_message(self, ctx: commands.Context) -> None:
        """Get the verified welcome message used to welcome verified users."""
        message = await self.verification_settings_store.get_verified_welcome_message(ctx.guild.id)
        if message is None:
            await ctx.send(f'The verified welcome message is not configured yet.', ephemeral=True)
        else:
            await ctx.send(f'The verified welcome message is `{message}`.', ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def set_verified_welcome_message(self, ctx: commands.Context, message: str) -> None:
        """Set the verified welcome message used to welcome verified users."""
        await self.verification_settings_store.set_verified_welcome_message(guild_id=ctx.guild.id, message=message)
        await ctx.send(f'The verified welcome message has been set to `{message}`.', ephemeral=True)

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


class VerificationRequest:
    """The in-memory representation of a user verification in the database."""

    def __init__(self, user_verification_id: int, guild_id: int, user_id: int, welcome_channel_id: int,
                 welcome_message_id: int, verified: bool,
                 joined_at: int, closed_at: Optional[int]) -> None:
        self.id = user_verification_id
        self.guild_id = guild_id
        self.user_id = user_id
        self.welcome_channel_id = welcome_channel_id
        self.welcome_message_id = welcome_message_id
        self.verified = verified
        self.joined_at = joined_at
        self.closed_at = closed_at


class VerificationSettingStore(BaseStore):
    """Handles database access with the `Settings` table for settings related to the verification system."""

    def __init__(self, db_loc: str) -> None:
        super().__init__(db_loc)

    async def get_welcome_channel_id(self, guild_id: int) -> int:
        channel_id = await self.get_setting(guild_id, 'welcome_channel_id')
        return channel_id

    async def set_welcome_channel_id(self, guild_id: int, channel_id: int) -> None:
        await self.set_setting(guild_id, 'welcome_channel_id', channel_id)

    async def get_verified_welcome_channel_id(self, guild_id: int) -> int:
        channel_id = await self.get_setting(guild_id, 'verified_welcome_channel_id')
        return channel_id

    async def set_verified_welcome_channel_id(self, guild_id: int, channel_id: int) -> None:
        await self.set_setting(guild_id, 'verified_welcome_channel_id', channel_id)

    async def get_verified_welcome_message(self, guild_id: int) -> str:
        message = await self.get_setting(guild_id, 'verified_welcome_message')
        return message

    async def set_verified_welcome_message(self, guild_id: int, message: str) -> None:
        await self.set_setting(guild_id, 'verified_welcome_message', message)

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


class VerificationRequestStore(BaseStore):
    """Handles database access with the `VerificationRequests` table."""

    def __init__(self, db_loc: str) -> None:
        super().__init__(db_loc)

    async def create(self, guild_id: int, user_id: int, welcome_channel_id: int,
                     welcome_message_id: int) -> VerificationRequest:
        async with aiosqlite.connect(self.db_loc) as con:
            statement = """INSERT INTO
                        VerificationRequests(
                            guild_id,
                            user_id,
                            welcome_channel_id,
                            welcome_message_id,
                            verified,
                            joined_at
                        )
                        VALUES (?, ?, ?, ?, FALSE, ?)
                        """
            joined_at = tools.unix_seconds_from_discord_snowflake_id(welcome_message_id)
            cur = await con.execute(statement, (guild_id, user_id, welcome_channel_id, welcome_message_id, joined_at))
            await con.commit()
            user_verification = VerificationRequest(user_verification_id=cur.lastrowid, guild_id=guild_id,
                                                    user_id=user_id, welcome_channel_id=welcome_channel_id,
                                                    welcome_message_id=welcome_message_id, verified=False,
                                                    joined_at=joined_at, closed_at=None)
            return user_verification

    async def close(self, verification_request: VerificationRequest, verified: bool) -> None:
        async with aiosqlite.connect(self.db_loc) as con:
            statement = """UPDATE VerificationRequests SET verified=?, closed_at=? WHERE id=?"""
            closed_at = int(time.time())
            await con.execute(statement, (verified, closed_at, verification_request.id))
            await con.commit()
            verification_request.verified = verified

    async def get_pending(self) -> List[VerificationRequest]:
        async with aiosqlite.connect(self.db_loc) as con:
            statement = 'SELECT * FROM VerificationRequests WHERE closed_at IS NULL'
            cur = await con.execute(statement)
            verification_requests_raw = await cur.fetchall()
            verification_requests = [
                VerificationRequest(
                    user_verification_id=user_verification_id,
                    guild_id=guild_id,
                    user_id=user_id,
                    welcome_channel_id=welcome_channel_id,
                    welcome_message_id=welcome_message_id,
                    verified=verified,
                    joined_at=joined_at,
                    closed_at=closed_at
                )
                for
                user_verification_id, guild_id, user_id, welcome_channel_id, welcome_message_id, verified, joined_at, closed_at
                in verification_requests_raw
            ]
            return verification_requests


class MissingWelcomeMessageError(Exception):
    """Exception raised when the welcome message for a particular verification request is missing."""
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
        # Get the welcome message. First, look if it is available in cache, otherwise, fetch it.
        if interaction.message.reference is not None:
            if interaction.message.reference.cached_message is None:
                channel = self.vs.bot.get_channel(interaction.message.reference.channel_id)
                welcome_message = await channel.fetch_message(interaction.message.reference.message_id)
            else:
                welcome_message = interaction.message.reference.cached_message
        else:
            raise MissingWelcomeMessageError()

        age_range = self.age_range_select.values
        age_range = age_range and age_range[0]
        gender = self.gender_select.values
        gender = gender and gender[0]

        _logger.info(f'{tools.user_string(interaction.user)} submitted the basic info {age_range=} and {gender=}.')

        if not gender or not age_range:
            await interaction.response.send_message(content='Please fill out both fields!', ephemeral=True)

        choose_advanced_info_modal = ChooseAdvancedInfoModal(verification_system=self.vs, age_range=age_range,
                                                             gender=gender, welcome_message=welcome_message)
        await interaction.response.send_modal(choose_advanced_info_modal)
        await interaction.edit_original_response(content='To retry, click the `Verify me!` button again.', view=None)


class ChooseAdvancedInfoModal(ui.Modal, title='Just a few more questions...'):
    """Asks the user about their reason for joining."""

    def __init__(self, verification_system: VerificationSystem, age_range: str, gender: str,
                 welcome_message: Message) -> None:
        super().__init__()

        self.vs = verification_system
        self.age_range = age_range
        assert age_range in ('12-15', '16-17', '18-29', '30-39', '40+')
        assert gender in ('male', 'female', 'non-binary')
        self.gender = gender
        self.welcome_message = welcome_message

        self.join_reason_text_input = ui.TextInput(
            label='Referrer',
            placeholder='How did you find out about this server?',
            required=True,
            max_length=100
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
        _logger.info(f'{tools.user_string(interaction.user)} submitted their verification request with '
                     f'{self.age_range=}, {self.gender=}, {self.join_reason_text_input.value=} and '
                     f'{self.additional_info_text_input.value=}.')

        # Get the verification channel.
        request_channel_id = await self.vs.verification_settings_store.get_request_channel_id(interaction.guild_id)
        request_channel = interaction.guild.get_channel(request_channel_id)

        # Open a new user verification request in the database.
        verification_request = await self.vs.verification_request_store.create(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
            welcome_channel_id=self.welcome_message.channel.id,
            welcome_message_id=self.welcome_message.id,
        )

        # Create the verification notification embed.
        description = f'User {interaction.user.mention} wants to be verified. They provided the following information.'
        embed = Embed(title='Verification Request', description=description, color=discord.Color.blue(),
                      timestamp=datetime.now(timezone.utc))
        embed.add_field(name='age range', value=self.age_range)
        embed.add_field(name='gender', value=self.gender)
        embed.add_field(name='join reason', value=self.join_reason_text_input.value)
        embed.add_field(name='additional info', value=self.additional_info_text_input.value)
        embed.set_author(name=tools.user_string(interaction.user),
                         url=f'https://discordapp.com/users/{interaction.user.id}',
                         icon_url=interaction.user.display_avatar)
        file = discord.File(self.vs.bot.img_dir / 'accept_reject.png', filename='image.png')
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
        if interaction.user.guild_permissions.manage_roles and interaction.user.guild_permissions.kick_members:
            return True
        else:
            _logger.info(f'{tools.user_string(interaction.user)} tried to verify or reject a verification request even '
                         'though they lack the necessary permissions.')
            await interaction.response.send_message('You are not allowed to do this action!')
            return False

    async def accept_verification_request(self, interaction: Interaction) -> None:
        # The lock and `is_finished()` call ensure that the view is only responded to once.
        async with self.lock:
            if self.is_finished():
                return

            # Retrieve the member this verification request belongs to.
            member = interaction.guild.get_member(self.verification_request.user_id)
            _logger.info(f"{tools.user_string(interaction.user)} accepted {tools.user_string(member)}'s "
                         "verification request.")

            # Assign the verification role to the user.
            # TODO Assign the other roles (gender and age range).
            role_id = await self.vs.verification_settings_store.get_role_id(interaction.guild_id)
            role = interaction.guild.get_role(role_id)
            await member.add_roles(role, reason='verify the user')

            # Store the decision to verify the user in the database.
            await self.vs.verification_request_store.close(self.verification_request, True)

            # Welcome the user with additional information in the verified welcome channel.
            verified_welcome_channel_id = await self.vs.verification_settings_store.get_verified_welcome_channel_id(
                interaction.guild_id
            )
            verified_welcome_channel = interaction.guild.get_channel(verified_welcome_channel_id)
            verified_welcome_message = await self.vs.verification_settings_store.get_verified_welcome_message(
                interaction.guild_id
            )
            description = verified_welcome_message.replace('<user>', member.mention)
            # embed = Embed(title=f'Welcome to {interaction.guild.name}!',
            #               description=description,
            #               color=discord.Color.green(),
            #               timestamp=datetime.now(timezone.utc))
            # embed.set_author(name=tools.user_string(interaction.user),
            #                  url=f'https://discordapp.com/users/{interaction.user.id}',
            #                  icon_url=interaction.user.display_avatar)
            # file = discord.File(self.vs.bot.img_dir / 'welcome2.png', filename='image.png')
            # embed.set_thumbnail(url='attachment://image.png')
            await verified_welcome_channel.send(content=description)

            # Remove the welcome message from the first welcome channel.
            # At this point, if it does not exist, we do not care.
            welcome_channel_id = self.verification_request.welcome_channel_id
            welcome_channel = self.vs.bot.get_channel(welcome_channel_id)
            welcome_message = await welcome_channel.fetch_message(self.verification_request.welcome_message_id)
            if welcome_message is not None:
                await welcome_message.delete()

            # Stop listening to the view and deactivate it.
            self.stop()
            self.remove_item(self.reject_button)
            self.accept_button.label = f'{self.accept_button.label}ed'
            self.accept_button.disabled = True

            # Edit the original verification notification embed.
            embed = interaction.message.embeds[0]
            embed.title += ' [ACCEPTED]'
            embed.colour = discord.Color.green()
            file = discord.File(self.vs.bot.img_dir / 'accepted_verification_request.png', filename='image.png')
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
        _logger.info(f"{tools.user_string(interaction.user)} rejected {tools.user_string(member)}'s verification "
                     f"request for {kick_reason=}.")
        await member.kick(reason=kick_reason)

        # Store the decision to not verify the user in the database.
        await self.vs.verification_request_store.close(self.verification_request, False)

        # Remove the welcome message from the first welcome channel.
        # At this point, if it does not exist, we do not care.
        welcome_channel_id = await self.vs.verification_settings_store.get_welcome_channel_id(
            guild_id=interaction.guild_id
        )
        welcome_channel = self.vs.bot.get_channel(welcome_channel_id)
        if welcome_channel is not None:
            welcome_message = await welcome_channel.fetch_message(self.verification_request.welcome_message_id)
            if welcome_message is not None:
                await welcome_message.delete()

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
            file = discord.File(self.vs.bot.img_dir / 'rejected_verification_request.png', filename='image.png')
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
