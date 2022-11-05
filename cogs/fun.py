import json
import logging
import random
import re
from typing import List, Optional

import toml
from discord import Message, User
from discord.ext import commands
from emoji import demojize, emojize

from main import SlimBot

_logger = logging.getLogger(__name__)


class Fun(commands.Cog, name='fun'):
    """A cog for fun gimmicks."""

    def __init__(self, bot: SlimBot) -> None:
        self.bot = bot
        self.pattern_to_action = []
        self.hug_links = []
        self._views_added = False

        config_file = self.bot.cog_dir / 'fun_config.toml'

        try:
            with open(config_file) as file:
                config = toml.load(file)
                self.hug_links = config['hug_links']
                self.pattern_to_action = [PatternToAction(pattern, actions['reactions'], actions['responses'])
                                          for pattern, actions in config['patterns'].items()]
        except (FileNotFoundError, json.JSONDecodeError, KeyError, re.error):
            logging.exception(f'Something went wrong opening {config_file}.')

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self.bot.wait_until_ready()
        if not self._views_added:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: Message) -> None:
        if message.author.bot:
            return

        for pattern_action in self.pattern_to_action:
            if pattern_action.match_lower(message.content):
                reaction = pattern_action.random_reaction()
                response = pattern_action.random_response()
                if reaction is not None:
                    await message.add_reaction(reaction)
                if response is not None:
                    await message.reply(content=response)
                break

    @commands.hybrid_command()
    async def hug(self, ctx: commands.Context, user: User):
        """Hug `user`."""
        hearts = emojize(":two_hearts:")
        if user == self.bot.user:
            await ctx.send(f'Hug myself? Let me give you a hug instead, {ctx.author.mention}! {hearts}')
        else:
            await ctx.send(f'Let me give you a hug, {user.mention}! {hearts}')
        await ctx.channel.send(random.choice(self.hug_links))


class PatternToAction:
    def __init__(self, pattern: str, reactions: List[str], responses: List[str]) -> None:
        """Represents a pattern and the possible emoji reactions and text responses that can be taken by the bot.
        If the pattern is invalid, raises `re.error`."""
        pattern = pattern.replace('\\\\', '\\')  # For some reason, the toml library doesn't do this itself.
        pattern = demojize(pattern)  # Some emojis have multiple unicode representations, so convert to text.
        pattern = pattern.replace('<mention>', r'!?(<@\d+>,? ?)')
        self.pattern = re.compile(pattern)
        self.reactions = [emojize(reaction) for reaction in reactions]
        self.responses = [emojize(response) for response in responses]

    def match_lower(self, string: str) -> bool:
        """Returns whether `string` matches the pattern. The check is case-insensitive."""
        string = demojize(string)  # Some emojis have multiple unicode representations, so convert to text.
        return bool(self.pattern.match(string.lower()))

    def random_reaction(self) -> Optional[str]:
        """Returns a random reaction from the list of possible reactions.
        If there are no reactions to choose from, returns `None`."""
        return random.choice(self.reactions) if self.reactions else None

    def random_response(self) -> Optional[str]:
        """Returns a random response from the list of possible responses.
        If there are no responses to choose from, returns `None`."""
        return random.choice(self.responses) if self.responses else None


async def setup(bot: SlimBot) -> None:
    await bot.add_cog(Fun(bot))
