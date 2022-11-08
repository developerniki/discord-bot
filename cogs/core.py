import logging

import discord
from discord.ext import commands

from slimbot import SlimBot, tools

_logger = logging.getLogger(__name__)


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
            return f'• **{ext[len(self.bot.config.ext_dir.name) + 1:]}** {"_(loaded)_" if loaded else "_(not loaded)_"}'

        loaded_extensions = self.bot.extensions.keys()
        extensions = [ext_str(ext, ext in loaded_extensions) for ext in self.bot.available_extensions()]
        extensions_str = '\n'.join(extensions)
        embed = discord.Embed(title='Extensions', description=extensions_str, color=discord.Color.purple())
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='load', hidden=True)
    @commands.has_guild_permissions(administrator=True)
    async def _load_extension(self, ctx: commands.Context, name: str):
        """Loads an extension."""
        try:
            await self.bot.load_extension(f'{self.bot.config.ext_dir.name}.{name}')
            _logger.info(f'{tools.user_string(ctx.author)} successfully loaded extension {name}.')
            embed = discord.Embed(title='Loaded Extension', description=f'Loaded **{name}**.',
                                  color=discord.Color.purple())
            await ctx.send(embed=embed, ephemeral=True)
        except commands.ExtensionNotFound:
            _logger.warning(
                f'{tools.user_string(ctx.author)} attempted to load extension {name} but it could not be found.'
            )
            embed = discord.Embed(title='Error while loading extension',
                                  description=f'Could not find extension **{name}**.',
                                  color=discord.Color.red())
            await ctx.send(embed=embed, ephemeral=True)
        except commands.ExtensionAlreadyLoaded:
            _logger.warning(
                f'{tools.user_string(ctx.author)} attempted to load extension {name} but it was already loaded.'
            )
            embed = discord.Embed(title='Error while loading extension',
                                  description=f'Extension **{name}** is already loaded.', color=discord.Color.red())
            await ctx.send(embed=embed, ephemeral=True)
        except commands.NoEntryPointError:
            _logger.warning(
                f'{tools.user_string(ctx.author)} attempted to load extension {name} but no entry point was found.'
            )
            embed = discord.Embed(title='Error while loading extension',
                                  description=f'Could not find extension **{name}**.', color=discord.Color.red())
            await ctx.send(embed=embed, ephemeral=True)
        except commands.ExtensionFailed:
            _logger.warning(
                f'{tools.user_string(ctx.author)} attempted to load extension {name} but it failed to load.'
            )
            embed = discord.Embed(
                title='Error while loading extension',
                description=f'Failed to load **{name}** during module execution or entry point setup.',
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='unload', hidden=True)
    @commands.has_guild_permissions(administrator=True)
    async def _unload_extension(self, ctx: commands.Context, name: str):
        """Unloads an extension."""
        try:
            await self.bot.unload_extension(f'{self.bot.config.ext_dir.name}.{name}')
            _logger.info(f'{tools.user_string(ctx.author)} successfully unloaded extension {name}.')
            embed = discord.Embed(title='Unloaded extension', description=f'Unloaded **{name}**.',
                                  color=discord.Color.purple())
            await ctx.send(embed=embed, ephemeral=True)
        except commands.ExtensionNotFound:
            _logger.warning(
                f'{tools.user_string(ctx.author)} attempted to unload extension {name} but it could not be found.'
            )
            embed = discord.Embed(title='Error while unloading extension',
                                  description=f'Could not find extension **{name}**.',
                                  color=discord.Color.red())
            await ctx.send(embed=embed, ephemeral=True)
        except commands.ExtensionNotLoaded:
            _logger.warning(
                f'{tools.user_string(ctx.author)} attempted to unload extension {name} but it was already unloaded.'
            )
            embed = discord.Embed(title='Error while unloading extension',
                                  description=f'Extension **{name}** is already unloaded.', color=discord.Color.red())
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='reload', hidden=True)
    @commands.has_guild_permissions(administrator=True)
    async def _reload_extension(self, ctx: commands.Context, name: str):
        """Reloads an extension."""
        try:
            await self.bot.reload_extension(f'{self.bot.config.ext_dir.name}.{name}')
            _logger.info(f'{tools.user_string(ctx.author)} successfully reloaded extension {name}.')
            embed = discord.Embed(title='Reloaded extension', description=f'Reloaded **{name}**.',
                                  color=discord.Color.purple())
            await ctx.send(embed=embed, ephemeral=True)
        except commands.ExtensionNotFound:
            _logger.warning(
                f'{tools.user_string(ctx.author)} attempted to reload extension {name} but it could not be found.'
            )
            embed = discord.Embed(title='Error while reloading extension',
                                  description=f'Could not find extension **{name}**.',
                                  color=discord.Color.red())
            await ctx.send(embed=embed, ephemeral=True)
        except commands.ExtensionNotLoaded:
            _logger.warning(
                f'{tools.user_string(ctx.author)} attempted to reload extension {name} but it was already unloaded.'
            )
            embed = discord.Embed(title='Error while reloading extension',
                                  description=f'Extension **{name}** is unloaded.', color=discord.Color.red())
            await ctx.send(embed=embed, ephemeral=True)
        except commands.NoEntryPointError:
            _logger.warning(
                f'{tools.user_string(ctx.author)} attempted to reload extension {name} but no entry point was found.'
            )
            embed = discord.Embed(title='Error while reloading extension',
                                  description=f'Could not find extension **{name}**.', color=discord.Color.red())
            await ctx.send(embed=embed, ephemeral=True)
        except commands.ExtensionFailed:
            _logger.warning(
                f'{tools.user_string(ctx.author)} attempted to reload extension {name} but it failed to load.'
            )
            embed = discord.Embed(
                title='Error while reloading extension',
                description=f'Failed to load **{name}** during module execution or entry point setup.',
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='sync', hidden=True)
    @commands.has_guild_permissions(administrator=True)
    async def _sync_commands(self, ctx: commands.Context):
        """Syncs all commands."""
        await self.bot.tree.sync()
        embed = discord.Embed(title='Sync', description=f'Synced all commands.', color=discord.Color.purple())
        await ctx.send(embed=embed, ephemeral=True)


async def setup(bot: SlimBot) -> None:
    await bot.add_cog(Core(bot))
