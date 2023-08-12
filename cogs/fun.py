import json
import logging
import random
import re
import tomllib
from typing import List, Optional

import emoji
from discord import User
from discord.ext import commands
from emoji import demojize, emojize

from slimbot import SlimBot, utils

_logger = logging.getLogger(__name__)


class Fun(commands.Cog, name='Fun'):
    """Contains fun gimmicks."""

    def __init__(self, bot: SlimBot) -> None:
        self.bot = bot
        self.pattern_to_action = []
        self.hug_links = []
        self._views_added = False

        config_file = self.bot.config.ext_dir / 'fun_config.toml'

        try:
            with open(config_file, mode='rb') as file:
                config = tomllib.load(file)
                self.hug_links = config['hug_links']
                self.pattern_to_action = [
                    PatternToAction(
                        pattern,
                        actions.get('reactions', []),
                        actions.get('responses', []),
                        actions.get('chance', 1.0)
                    )
                    for pattern, actions in config['patterns'].items()
                ]
        except (FileNotFoundError, json.JSONDecodeError, KeyError, re.error):
            _logger.exception(f'Something went wrong opening {config_file}.')

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self.bot.wait_until_ready()
        if not self._views_added:
            pass

    # @commands.Cog.listener()
    # async def on_message(self, message: Message) -> None:
    #     if message.author.bot:
    #         return
    #
    #     for pattern_action in self.pattern_to_action:
    #         if pattern_action.match_lower_with_chance(message.content):
    #             _logger.info(f'Responding to pattern in message "{message.content}" by user '
    #                          f'{utils.user_string(message.author)}.')
    #             reaction = pattern_action.random_reaction()
    #             response = pattern_action.random_response()
    #             if reaction is not None:
    #                 await message.add_reaction(reaction)
    #             if response is not None:
    #                 await message.reply(content=response)
    #             break

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
    async def bonk(self, ctx: commands.Context, user: User):
        """Bonk `user`."""
        angry = emojize(':angry_face:')
        bonk_link = 'https://tenor.com/view/bonk-v%C3%A0o-m%E1%BA%B7t-c%C3%A1i-c%C3%A1m-bonk-anime-bonk-meme-bonk-dog-gif-26069974'

        if user == self.bot.user:
            await ctx.send(f'Bonk myself? Let me bonk you instead, {ctx.author.mention}! {angry}')
        else:
            await ctx.send(f'No horni, {user.mention}! {angry}')
        await ctx.channel.send(bonk_link)

    @commands.hybrid_command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def cat(self, ctx: commands.Context):
        """Reply with a cat picture."""
        cat_picture_url = await fetch_cat_picture_url()
        await ctx.send(cat_picture_url)

    @commands.hybrid_command()
    async def choice(self, ctx: commands.Context, *, choices: str):
        """Make the bot choose between `n` comma-separated choices."""
        choices = choices.split(',')
        if len(choices) < 2:
            await ctx.send('Please write at least two coma-separated options.')
        else:
            dance_emojis = [':sparkles:', ':man_dancing:', ':woman_dancing:', ':musical_notes:',
                            ':person_cartwheeling:', ':people_with_bunny_ears:']
            await ctx.send(
                f'{emoji.emojize(random.choice(dance_emojis))} '
                '_Eeny, meeny, miny, moe. Catch a tiger by the toe. If he hollers, let him go. Eeny, meeny, miny, moe._ '
                f'{ctx.author.mention}, I choose... ```{random.choice(choices).strip()}```'
            )


class PatternToAction:
    def __init__(self, pattern: str, reactions: List[str], responses: List[str], chance: float) -> None:
        """Represents a pattern and the possible emoji reactions and text responses that can be taken by the bot.
        `0 <= chance <= 1` is the probability the `match_lower_with_chance` method will return `True` if the match is
        valid. If the pattern is invalid, raises `re.error`.
        """
        assert 0 <= chance <= 1
        pattern = pattern.replace('\\\\', '\\')  # For some reason, the toml library doesn't do this itself.
        pattern = demojize(pattern)  # Some emojis have multiple unicode representations, so convert to text.
        pattern = pattern.replace('<user>', r'!?(<@\d+>,? ?)')  # Allows to match a tagged user.
        # Don't begin or end the pattern with a non-whitespce, but allow ending it with `,`, `.`, and `!`.
        pattern = r'(?<!\S)' + f'({pattern})' + r'[,.!]?(?!\S)'
        self.pattern = re.compile(pattern)
        self.reactions = [emojize(reaction) for reaction in reactions]
        self.responses = [emojize(response) for response in responses]
        self.chance = chance

    def match_lower(self, string: str) -> bool:
        """Returns whether `string` matches the pattern. The check is case-insensitive.
        """
        string = demojize(string)  # Some emojis have multiple unicode representations, so convert to text.
        return bool(self.pattern.search(string.lower()))

    def match_lower_with_chance(self, string: str) -> bool:
        """Like `match_lower` but a valid match only returns `True` in `self.chance` cases.
        """
        return random.random() < self.chance and self.match_lower(string)

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
    return await utils.fetch_html_escaped_string_from_api(url=url, key=key, default=default, from_list=True)


async def setup(bot: SlimBot) -> None:
    await bot.add_cog(Fun(bot))
