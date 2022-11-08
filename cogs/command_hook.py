import logging
from typing import Any

import discord
from discord.ext import commands

from slimbot import SlimBot, tools

_logger = logging.getLogger(__name__)


class CommandHook(commands.Cog, name='command_hook'):
    """Logs the commands being used and handles command errors."""

    def __init__(self, bot: SlimBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, exception: commands.CommandError) -> None:
        exception = getattr(exception, 'original', exception)

        if hasattr(ctx.command, 'on_error'):
            # Has local handler, so return.
            return
        elif ctx.cog and ctx.cog._get_overridden_method(ctx.cog.cog_command_error) is not None:
            # Has cog handler, so return.
            return
        elif isinstance(exception, commands.CommandNotFound):
            _logger.warning(f'Command {ctx.command} was not found.')
            await ctx.send(str(exception), ephemeral=True)
            return
        elif isinstance(exception, commands.DisabledCommand):
            _logger.warning(f'Command {ctx.command} is disabled.')
            await ctx.send(str(exception), ephemeral=True)
        elif isinstance(exception, commands.NoPrivateMessage):
            try:
                _logger.warning(f'Command {ctx.command} cannot be used in private messages.')
                await ctx.send(str(exception), ephemeral=True)
            except discord.HTTPException:
                pass
        elif isinstance(exception, commands.MissingPermissions):
            _logger.warning(f'The user has insufficient permissions to use {ctx.command}')
            await ctx.send(str(exception), ephemeral=True)
        else:
            _logger.error(f'Ignoring exception `{str(exception)}` in command {ctx.command}.', exc_info=exception)

    @staticmethod
    def __command_string(ctx: commands.Context) -> str:
        def to_string(x: Any) -> str:
            match x:
                case discord.User() | discord.Member() | discord.abc.GuildChannel():
                    return x.mention
                case _:
                    return str(x)

        args = ', '.join(str(arg) for arg in ctx.args[2:])
        kwargs = ', '.join([f'{key}={to_string(value)}' for key, value in ctx.kwargs.items()])
        arg_string = ', '.join([x for x in (args, kwargs) if x != ''])

        res = f'{ctx.prefix}{ctx.command.cog.qualified_name or ""}.{ctx.command.qualified_name or ""}({arg_string})'
        return res

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context) -> None:
        _logger.info(f'{tools.user_string(ctx.author)} used `{self.__command_string(ctx)}` (invoked).')

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context) -> None:
        _logger.info(f'{tools.user_string(ctx.author)} used `{self.__command_string(ctx)}` (completed).')


async def setup(bot) -> None:
    await bot.add_cog(CommandHook(bot))
