import logging
import re
from typing import Any

import discord
from discord.ext import commands

from slimbot import SlimBot, tools

_logger = logging.getLogger(__name__)


class CommandHook(commands.Cog, name='Command Hook'):
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
            # Do some hacky stuff to print a prettier error message.
            arg0 = exception.args[0] if exception.args else ''
            command_search = re.fullmatch('Command "(.+)" is not found', arg0)
            command = command_search.group(1) if command_search else None

            if not command:
                _logger.error('Something about the `commands.CommandNotFound` error message changed;'
                              'the hack used in the command hook does not work anymore.')
                return

            # Repeating the command prefix should not be an error.
            command_prefix = await self.bot.core_store.get_command_prefix(ctx.guild.id)
            if re.match(f'{re.escape(command_prefix)}+', command):
                return

            # Finally, print the error message.
            msg = 'Command '
            if command is not None:
                msg += f'`{command}` '
            msg += 'was not found.'
            _logger.info(msg)
            await ctx.send(msg, ephemeral=True)
        elif isinstance(exception, commands.DisabledCommand):
            msg = f'Command {ctx.command} is disabled.'
            _logger.info(msg)
            await ctx.send(msg, ephemeral=True)
        elif isinstance(exception, commands.NoPrivateMessage):
            msg = f'Command {ctx.command} cannot be used in private messages.'
            _logger.info(msg)
            await ctx.send(msg, ephemeral=True)
        elif isinstance(exception, commands.MissingPermissions):
            msg = f'The user has insufficient permissions to use {ctx.command}'
            _logger.warning(msg)
            await ctx.send(msg, ephemeral=True)
        else:
            _logger.error(f'Ignoring exception `{str(exception)}` in command {ctx.command}.', exc_info=exception)
            await ctx.send('There was an unexpected error!', ephemeral=True)

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
