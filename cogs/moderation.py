import logging
from typing import Optional

from discord import TextChannel
from discord.ext import commands

from slimbot import SlimBot, tools

_logger = logging.getLogger(__name__)


class Moderation(commands.Cog, name='Moderation'):
    """Help with simple moderation tasks."""

    def __init__(self, bot: SlimBot) -> None:
        self.bot = bot

    @commands.hybrid_command(aliases=['echo'])
    @commands.has_permissions(send_messages=True, manage_messages=True)
    async def say(self, ctx: commands.Context, channel: Optional[TextChannel], *, message: str) -> None:
        """Make the bot say `message` in `channel`."""
        if channel is None:
            channel = ctx.channel
        await channel.send(message)
        await ctx.send(f'Sent the following message in {channel.mention}:\n{tools.quote_message(message)}',
                       ephemeral=True)

    @commands.hybrid_command()
    @commands.has_guild_permissions(manage_channels=True)
    async def ping(self, ctx: commands.Context) -> None:
        """Do a ping test and report the latency."""
        await ctx.send(f'pong! {round(1_000 * self.bot.latency)} ms', ephemeral=True)

    @commands.hybrid_command(aliases=['hl'])
    async def helpline(self, ctx: commands.Context) -> None:
        """Send link to website with suicide prevention helplines."""
        await ctx.send('https://findahelpline.com/')


async def setup(bot: SlimBot) -> None:
    await bot.add_cog(Moderation(bot))
