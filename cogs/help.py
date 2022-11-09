from typing import Optional

import discord
from discord.ext import commands

from slimbot import SlimBot

HIDDEN_MODULES = ('Core', 'Command Hook')


class Help(commands.Cog, name='Help'):
    """Handles help messages."""

    def __init__(self, bot: SlimBot) -> None:
        self.bot = bot
        self.bot.remove_command('help')

    @commands.hybrid_command()
    async def help(self, ctx: commands.Context, cog: Optional[str]) -> None:
        """Shows descriptions of all bot modules and commands."""
        if cog is None:
            embed = discord.Embed(title='Commands & Modules',
                                  color=discord.Color.purple(),
                                  description=f'Use `/help <module>` for more information.')

            # Iterate through the cogs and gather their descriptions.
            cogs = [cog for cog in self.bot.cogs if cog not in HIDDEN_MODULES]
            cog_descriptions = [f'• __**{cog}:**__ {self.bot.cogs[cog].__doc__}' for cog in cogs]
            cog_descriptions = [description.strip().replace("\\n", " ") for description in cog_descriptions]
            cog_descriptions = '\n'.join(cog_descriptions)

            other_descriptions = [
                f'• __**{command.name}:**__ {command.help}'
                for command in self.bot.walk_commands()
                if not command.cog_name and not command.hidden
            ]
            other_descriptions = '\n'.join(other_descriptions)

            # Add the command descriptions to the embed.
            if cog_descriptions:
                embed.add_field(name='Module Commands', value=cog_descriptions)
            if other_descriptions:
                embed.add_field(name='Other Commands', value=other_descriptions)
        else:
            bot_cog = [cog_ for cog_ in self.bot.cogs if cog.lower() == cog_.lower()]
            bot_cog = bot_cog and bot_cog[0]

            if bot_cog and bot_cog.lower() not in [m.lower() for m in HIDDEN_MODULES]:
                embed = discord.Embed(
                    title=f"Module '{bot_cog}' Commands",
                    description=self.bot.cogs[bot_cog].__doc__,
                    color=discord.Color.purple(),
                )
                for command in self.bot.get_cog(bot_cog).get_commands():
                    if command.hidden:
                        continue
                    if isinstance(command, discord.ext.commands.Group):
                        for command_ in command.commands:
                            if command_.hidden:
                                continue
                            if isinstance(command_, discord.ext.commands.Group):
                                for command__ in command_.commands:
                                    if command__.hidden:
                                        continue
                                    name = f'{command.name} {command_.name} {command__.name}'
                                    help_str = command__.help
                                    embed.add_field(name=f'• __**/{name}**__', value=help_str, inline=False)
                            else:
                                name = f'{command.name} {command_.name}'
                                help_str = command_.help
                                embed.add_field(name=f'• __**/{name}**__', value=help_str, inline=False)
                    else:
                        name = command.name
                        help_str = command.help
                        embed.add_field(name=f'• __**/{name}**__', value=help_str, inline=False)
            else:
                embed = discord.Embed(
                    title='Module Not Found',
                    description=f"Module '{cog}' not found.",
                    color=discord.Color.purple()
                )

        await ctx.send(embed=embed, ephemeral=True)


async def setup(bot) -> None:
    await bot.add_cog(Help(bot))
