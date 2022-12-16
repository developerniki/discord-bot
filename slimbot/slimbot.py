import logging

import discord
from discord.ext import commands

from database import database, CommandPrefixStore
from .config import Config

_logger = logging.getLogger(__name__)


class SlimBot(commands.Bot):
    """The main class of this application."""

    def __init__(self, config: Config) -> None:
        self.config = config

        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        self.command_prefix_store = CommandPrefixStore(self.config.db_file)

        async def command_prefix(bot: commands.Bot, message: discord.Message):
            prefixes = [bot.user.name + ' ']
            if message.guild is not None:
                guild_prefix = await self.command_prefix_store.get_command_prefix(message.guild.id)
                prefixes.append(guild_prefix)

            # Allow case-insensitive prefix.
            prefixes = [message.content[:len(prefix)] if message.content.lower().startswith(prefix.lower())
                        else prefix for prefix in prefixes]

            return commands.when_mentioned_or(*prefixes)(bot, message)

        super().__init__(command_prefix=command_prefix, intents=intents, case_insensitive=True)

    def available_extensions(self):
        return [
            f'{self.config.ext_dir.name}.{entry.stem}'
            for entry in self.config.ext_dir.iterdir()
            if entry.suffix == '.py'
        ]

    async def setup_hook(self) -> None:
        await database.do_migrations(db_file=self.config.db_file, defaults=self.config.defaults)
        _logger.info('Did the database migrations.')

        for ext in self.available_extensions():
            await self.load_extension(ext)
        await self.tree.sync()
        _logger.info(f'Loaded extensions and synced slash commands for {self.user}.')

    async def on_ready(self) -> None:
        _logger.info(f'The bot has logged in as {self.user}!')
