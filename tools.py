import html

import aiohttp
from aiohttp import ContentTypeError, ClientConnectorError
from discord import User, Member


def quote_message(message: str):
    """Quote a string in Discord format."""
    return '> ' + message.strip().replace('\n', '\n> ')


def user_string(user: User | Member) -> str:
    """Given a `User` or `Member`, return a string containing the user's name, discriminator, and user ID."""
    return f'{user.name}#{user.discriminator} ({user.id})'


def unix_seconds_from_discord_snowflake_id(snowflake_id: int) -> int:
    """Converts a Discord snowflake ID to a unix timestamp in seconds as described here:
    https://discord.com/developers/docs/reference#snowflakes"""
    discord_epoch = 1_420_070_400_000
    return ((snowflake_id >> 22) + discord_epoch) // 1_000


async def fetch_from_api(url: str, default: str) -> str:
    """Fetch a string from some web API.

    Positional arguments:
    url -- the URL to fetch
    default -- return this if the request failed or returned None or an empty string
    """
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    resp = await resp.json()
                    result = resp.get('insult')
                else:
                    result = None
        except ClientConnectorError | ContentTypeError:
            result = None

    result = result or default

    # Unescape HTML entities like `&quot;`.
    result = html.unescape(result)

    return result


async def fetch_insult() -> str:
    """Fetch an insult from the evilinsult.com API."""
    url = 'https://evilinsult.com/generate_insult.php?lang=en&type=json'
    default = 'You suck!'
    return await fetch_from_api(url, default)


async def fetch_insult_filter_you(max_retries=10) -> str:
    """Fetch an insult from the evilinsult.com API until a response contains the word 'you'. Tries at most ten times.
    Set `max_retries` to 0 to query the API an indefinite number of times."""
    insult = ''
    while 'you' not in insult.lower() and max_retries > 0:
        insult = await fetch_insult()
    return insult
