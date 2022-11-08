import json
import logging
import random
import re
from typing import List, Optional

import toml
from discord import Message, User
from discord.ext import commands
from emoji import demojize, emojize

from slimbot import SlimBot, tools

_logger = logging.getLogger(__name__)


class Fun(commands.Cog, name='fun'):
    """A cog for fun gimmicks."""

    def __init__(self, bot: SlimBot) -> None:
        self.bot = bot
        self.pattern_to_action = []
        self.hug_links = []
        self._views_added = False

        config_file = self.bot.config.ext_dir / 'fun_config.toml'

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
                _logger.info(f'Found pattern in message "{message.content}" by user '
                             f'{tools.user_string(message.author)}.')
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

    @commands.hybrid_command()
    async def cat(self, ctx: commands.Context):
        """Reply with a cat picture."""
        cat_picture_url = await fetch_cat_picture_url()
        await ctx.send(cat_picture_url)


class PatternToAction:
    def __init__(self, pattern: str, reactions: List[str], responses: List[str]) -> None:
        """Represents a pattern and the possible emoji reactions and text responses that can be taken by the bot.
        If the pattern is invalid, raises `re.error`.
        """
        pattern = pattern.replace('\\\\', '\\')  # For some reason, the toml library doesn't do this itself.
        pattern = demojize(pattern)  # Some emojis have multiple unicode representations, so convert to text.
        pattern = pattern.replace('<mention>', r'!?(<@\d+>,? ?)')
        self.pattern = re.compile(pattern)
        self.reactions = [emojize(reaction) for reaction in reactions]
        self.responses = [emojize(response) for response in responses]

    def match_lower(self, string: str) -> bool:
        """Returns whether `string` matches the pattern. The check is case-insensitive.
        """
        string = demojize(string)  # Some emojis have multiple unicode representations, so convert to text.
        return bool(self.pattern.match(string.lower()))

    def random_reaction(self) -> Optional[str]:
        """Returns a random reaction from the list of possible reactions.
        If there are no reactions to choose from, returns `None`.
        """
        return random.choice(self.reactions) if self.reactions else None

    def random_response(self) -> Optional[str]:
        """Returns a random response from the list of possible responses.
        If there are no responses to choose from, returns `None`.
        """
        return random.choice(self.responses) if self.responses else None


async def fetch_cat_picture_url() -> str:
    """Fetch a cat picture from the `thecatapi.com` API."""
    url = 'https://api.thecatapi.com/v1/images/search?format=json'
    key = 'url'
    default = random.choice([
        'https://upload.wikimedia.org/wikipedia/commons/b/bb/Kittyply_edit1.jpg',
        'https://en.wikipedia.org/wiki/Cat#/media/File:Domestic_Cat_Face_Shot.jpg',
        'https://en.wikipedia.org/wiki/Cat#/media/File:Felis_catus-cat_on_snow.jpg',
        'https://en.wikipedia.org/wiki/Cat#/media/File:Black_Cat_(7983739954).jpg',
    ])
    return await tools.fetch_html_escaped_string_from_api(url=url, key=key, default=default, from_list=True)


async def fetch_insult() -> str:
    """Fetch an insult from the evilinsult.com API."""
    url = 'https://evilinsult.com/generate_insult.php?lang=en&type=json'
    key = 'insult'
    default = 'You suck!'
    return await tools.fetch_html_escaped_string_from_api(url=url, key=key, default=default)


async def fetch_insult_filter_you(max_retries=10) -> str:
    """Fetch an insult from the evilinsult.com API until a response contains the word 'you'. Tries at most ten times.
    Set `max_retries` to 0 to query the API an indefinite number of times.
    """
    insult = ''
    while 'you' not in insult.lower() and max_retries > 0:
        insult = await fetch_insult()
    return insult


async def setup(bot: SlimBot) -> None:
    await bot.add_cog(Fun(bot))
