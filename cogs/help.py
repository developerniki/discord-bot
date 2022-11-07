from typing import Optional

import discord
from discord.ext import commands

from main import SlimBot


class Help(commands.Cog, name='help'):
    """A help message cog."""

    def __init__(self, bot: SlimBot) -> None:
        self.bot = bot
        self.bot.remove_command('help')

    @commands.hybrid_command()
    async def help(self, ctx: commands.Context, cog: Optional[str]) -> None:
        """Shows all bot modules."""
        if cog is None:
            embed = discord.Embed(title='Commands & Modules',
                                  color=discord.Color.purple(),
                                  description=f'Use `/help <module>` for more information.')

            # Iterate through the cogs and gather their descriptions.
            cog_descriptions = [f'• __**{cog}:**__ {self.bot.cogs[cog].__doc__}' for cog in self.bot.cogs]
            cog_descriptions = '\n'.join(cog_descriptions)

            other_descriptions = [
                f'• **{command.name}:** {command.help}'
                for command in self.bot.walk_commands()
                if not command.cog_name and not command.hidden
            ]
            other_descriptions = '\n'.join(other_descriptions)

            # Add the command descriptions to the embed.
            if cog_descriptions:
                embed.add_field(name='Module Commands', value=cog_descriptions, inline=False)
            if other_descriptions:
                embed.add_field(name='Other Commands', value=other_descriptions, inline=False)
        else:
            bot_cog = [cog_ for cog_ in self.bot.cogs if cog.lower() == cog_.lower()]
            bot_cog = bot_cog and bot_cog[0]

            if bot_cog is not None:
                embed = discord.Embed(
                    title=f"Module '{bot_cog}' Commands",
                    description=self.bot.cogs[bot_cog].__doc__,
                    color=discord.Color.purple(),
                )
                commands = [command for command in self.bot.get_cog(bot_cog).get_commands() if not command.hidden]
                for command in commands:
                    embed.add_field(name=f'• __**/{command.name}**__', value=command.help, inline=False)
            else:
                embed = discord.Embed(
                    title='Module Not Found',
                    description=f'Module {bot_cog} not found.',
                    color=discord.Color.purple()
                )

        await ctx.send(embed=embed, ephemeral=True)


async def setup(bot) -> None:
    await bot.add_cog(Help(bot))
