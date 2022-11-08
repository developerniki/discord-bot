import logging
from pathlib import Path

import aiosqlite
import discord
from discord.ext import commands

from .config import Config
from .store import CoreStore

_logger = logging.getLogger(__name__)


class SlimBot(commands.Bot):
    """The main class of this application."""

    def __init__(self, config: Config) -> None:
        self.config = config

        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        self.core_store = CoreStore(self.config.db_file)

        async def command_prefix(bot: commands.Bot, message: discord.Message):
            prefixes = [bot.user.name + ' ']
            if message.guild is not None:
                guild_prefix = await self.core_store.get_command_prefix(message.guild.id)
                prefixes.append(guild_prefix)

            # Allow case-insensitive prefix.
            prefixes = [message.content[:len(prefix)] if message.content.lower().startswith(prefix.lower())
                        else prefix for prefix in prefixes]

            return commands.when_mentioned_or(*prefixes)(bot, message)

        super().__init__(command_prefix=command_prefix, intents=intents, case_insensitive=True)

    async def do_migrations(self) -> None:
        """Do the database migrations by creating all the tables and moving the default settings to the DefaultSettings
        table."""
        with open(self.config.migr_dir / '0__create_dbs.sql') as file:
            sql_script = file.read()

        Path(self.config.db_file).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.config.db_file) as con:
            await con.executescript(sql_script)
            await con.execute('DELETE FROM DefaultSettings')
            await con.executemany('INSERT INTO DefaultSettings (k, v) VALUES (?, ?)', self.config.defaults.items())
            await con.commit()

    def available_extensions(self):
        return [
            f'{self.config.ext_dir.name}.{entry.stem}'
            for entry in self.config.ext_dir.iterdir()
            if entry.suffix == '.py'
        ]

    async def setup_hook(self) -> None:
        await self.do_migrations()
        _logger.info('Did the database migrations.')

        for ext in self.available_extensions():
            await self.load_extension(ext)
        await self.tree.sync()
        _logger.info(f'Loaded extensions and synced slash commands for {self.user}.')

    async def on_ready(self) -> None:
        _logger.info(f'The bot has logged in as {self.user}!')
