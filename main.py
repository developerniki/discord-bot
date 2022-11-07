import logging.handlers
from pathlib import Path
from typing import Any

import aiosqlite
import discord
import toml
from discord import Message
from discord.ext import commands

_logger = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).parent.resolve()
CFG_LOC = ROOT_DIR / 'config.toml'
DEFAULT_CONFIG = """# token = '<uncomment this line and insert your Discord token here>'

[defaults]
# These settings only apply if server-specific settings don't overwrite them.
command_prefix = '?'
ticket_cooldown = 3600

[paths]
database = 'data.db'
log = 'logs/slimbot.log'
cogs = 'cogs'
images = 'images'
migrations = 'migrations'
"""
config_file = Path(CFG_LOC)
if not config_file.exists():
    config_file.write_text(DEFAULT_CONFIG)
CONFIG = toml.loads(config_file.read_text())


class SlimBot(commands.Bot):
    """The main class of this application."""

    def __init__(self) -> None:
        self.root_dir = ROOT_DIR
        self.cog_dir = self.root_dir / CONFIG['paths']['cogs']
        self.img_dir = self.root_dir / CONFIG['paths']['images']
        self.mig_dir = self.root_dir / CONFIG['paths']['migrations']

        self.cfg_loc = self.root_dir / 'config.toml'
        self.db_loc = self.root_dir / CONFIG['paths']['database']
        self.log_loc = self.root_dir / CONFIG['paths']['log']

        self.extension_prefix = CONFIG['paths']['cogs']

        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        self.core_store = CoreStore(self.db_loc)

        async def command_prefix(bot: commands.Bot, message: discord.Message):
            guild_prefix = await self.core_store.get_command_prefix(message.guild.id)
            prefixes = (guild_prefix, bot.user.name + ' ')
            return commands.when_mentioned_or(*prefixes)(bot, message)

        super().__init__(command_prefix=command_prefix, intents=intents, case_insensitive=True)

    async def do_migrations(self) -> None:
        """Do the database migrations by creating all the tables and moving the default settings to the DefaultSettings
        table."""
        with open(self.mig_dir / '0__create_dbs.sql') as file:
            sql_script = file.read()

        Path(self.db_loc).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_loc) as con:
            await con.executescript(sql_script)
            await con.execute('DELETE FROM DefaultSettings')
            await con.executemany('INSERT INTO DefaultSettings (k, v) VALUES (?, ?)', CONFIG['defaults'].items())
            await con.commit()

    def available_extensions(self):
        return [
            f'{self.extension_prefix}.{entry.stem}'
            for entry in (self.root_dir / 'cogs').iterdir()
            if entry.suffix == '.py'
        ]

    async def setup_hook(self) -> None:
        await self.do_migrations()
        _logger.info('Did the database migrations.')

        await self.add_cog(Core(self))  # Add the core cog.
        for ext in self.available_extensions():
            await self.load_extension(ext)
        await self.tree.sync()
        _logger.info(f'Loaded extensions and synced slash commands for {self.user}.')

    async def on_ready(self) -> None:
        _logger.info(f'The bot has logged in as {self.user}!')

    async def on_message(self, message: Message) -> None:
        # Make prefix case-insensitive.
        prefixes = await self.get_prefix(message)
        if isinstance(prefixes, str):
            prefixes = [prefixes]

        for prefix in prefixes:
            if message.content.lower().startswith(prefix.lower()):
                message.content = prefix + message.content[len(prefix):]
                break

        await self.process_commands(message)


class Core(commands.Cog, name='core'):
    """This cog contains the core functionality of the bot."""

    def __init__(self, bot: SlimBot) -> None:
        self.bot = bot

    @commands.hybrid_command(name='get_command_prefix')
    async def _get_command_prefix(self, ctx: commands.Context) -> None:
        """Get the command prefix."""
        command_prefix = await self.bot.core_store.get_command_prefix(ctx.guild.id)
        await ctx.send(f"The server's command prefix is `{command_prefix}`.", ephemeral=True)

    @commands.hybrid_command(name='set_command_prefix')
    @commands.has_guild_permissions(administrator=True)
    async def _set_command_prefix(self, ctx: commands.Context, command_prefix: str) -> None:
        """Set the command prefix."""
        await self.bot.core_store.set_command_prefix(guild_id=ctx.guild.id, command_prefix=command_prefix)
        await ctx.send(f'Server command prefix set to `{command_prefix}`.', ephemeral=True)

    @commands.hybrid_command(name='get_extensions', hidden=True)
    @commands.has_guild_permissions(administrator=True)
    async def _get_extensions(self, ctx: commands.Context):
        """Get the available extensions and their loaded status."""

        def ext_str(ext: str, loaded: bool):
            return f'• **{ext[len(self.bot.extension_prefix) + 1:]}** {"_(loaded)_" if loaded else "_(not loaded)_"}'

        loaded_extensions = self.bot.extensions.keys()
        extensions = [ext_str(ext, ext in loaded_extensions) for ext in self.bot.available_extensions()]
        extensions_str = '\n'.join(extensions)
        embed = discord.Embed(title='Extensions', description=extensions_str, color=discord.Color.purple())
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='load', hidden=True)
    @commands.has_guild_permissions(administrator=True)
    async def _load_extension(self, ctx: commands.Context, name: str):
        """Loads an extension."""
        await self.bot.load_extension(f'{self.bot.extension_prefix}.{name}')
        embed = discord.Embed(title='Loaded Extension', description=f'Loaded **{name}**.', color=discord.Color.purple())
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='unload', hidden=True)
    @commands.has_guild_permissions(administrator=True)
    async def _unload_extension(self, ctx: commands.Context, name: str):
        """Unloads an extension."""
        await self.bot.unload_extension(f'{self.bot.extension_prefix}.{name}')
        embed = discord.Embed(title='Unloaded extension', description=f'Unloaded **{name}**.',
                              color=discord.Color.purple())
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='reload', hidden=True)
    @commands.has_guild_permissions(administrator=True)
    async def _reload_extension(self, ctx: commands.Context, name: str):
        """Reloads an extension."""
        await self.bot.reload_extension(f'{self.bot.extension_prefix}.{name}')
        embed = discord.Embed(title='Reloaded extension', description=f'Reloaded **{name}**.',
                              color=discord.Color.purple())
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='sync', hidden=True)
    @commands.has_guild_permissions(administrator=True)
    async def _sync_commands(self, ctx: commands.Context):
        """Syncs all commands."""
        await self.bot.tree.sync()
        embed = discord.Embed(title='Sync', description=f'Synced all commands.', color=discord.Color.purple())
        await ctx.send(embed=embed, ephemeral=True)


class BaseStore:
    """The base storage class which is inherited by all classes that handle database interactions."""

    def __init__(self, db_loc: str):
        self.db_loc = db_loc

    async def get_default_setting(self, key: Any) -> Any:
        """Return the default setting for `key`."""
        async with aiosqlite.connect(self.db_loc) as con:
            statement = 'SELECT v FROM DefaultSettings WHERE k=?'
            cur = await con.execute(statement, (key,))
            res = await cur.fetchone()
            res = res and res[0]
            return res

    async def get_setting(self, guild_id: int, key: Any) -> Any:
        """Return the server specific setting for `key` and the default setting for `key` if none exists."""
        async with aiosqlite.connect(self.db_loc) as con:
            statement = """SELECT IFNULL(S.v, D.v)
                        FROM (SELECT * FROM Settings WHERE guild_id = ?) S
                        FULL JOIN DefaultSettings D ON S.k = D.k
                        WHERE ? IN (S.k, D.k)
                        """
            cur = await con.execute(statement, (guild_id, key))
            res = await cur.fetchone()
            res = res and res[0]
            return res

    async def set_setting(self, guild_id: int, key: Any, value: Any) -> None:
        """Set the server-specific setting for `key`."""
        async with aiosqlite.connect(self.db_loc) as con:
            statement = 'INSERT OR REPLACE INTO Settings(guild_id, k, v) VALUES (?, ?, ?)'
            await con.execute(statement, (guild_id, key, value))
            await con.commit()


class CoreStore(BaseStore):
    """The storage class that handles database interaction relevant to the core functions of the bot."""

    def __init__(self, db_loc: str) -> None:
        super().__init__(db_loc)

    async def get_command_prefix(self, guild_id: int) -> str:
        return await self.get_setting(guild_id, 'command_prefix')

    async def set_command_prefix(self, guild_id: int, command_prefix: str) -> None:
        await self.set_setting(guild_id, 'command_prefix', command_prefix)


def setup_logging(log_loc):
    # Set only the root logger from which all loggers derive their config (Python's logging is hierarchical).
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    dt_fmt = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')

    console_log_handler = logging.StreamHandler()
    console_log_handler.setFormatter(formatter)

    Path(log_loc).parent.mkdir(parents=True, exist_ok=True)
    file_log_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_loc,
        encoding='utf-8',
        when='midnight',
        utc=True
    )
    file_log_handler.setFormatter(formatter)

    logger.addHandler(console_log_handler)
    logger.addHandler(file_log_handler)


if __name__ == '__main__':
    bot = SlimBot()
    try:
        setup_logging(bot.log_loc)
        bot.run(CONFIG['token'], log_handler=None)  # Set `log_handler` to `None` as we manually set up logging.
    except KeyError as err:
        _logger.exception(f'Key `token` not found in {CFG_LOC}.')
