import html
from pathlib import Path

import aiohttp
from aiohttp import ContentTypeError, ClientConnectorError
from discord import User, Member

DEFAULT_CONFIG = """token = '<insert your Discord token here>'

[defaults]
# These settings only apply if server-specific settings don't overwrite them.
command_prefix = '?'
ticket_cooldown = 3600

[paths]
database = 'data.db'
log = 'logs/slimbot.log'
cogs = 'cogs'
images = 'images'
migrations = 'migrations'
"""


def generate_config(location):
    """If the config.toml file does not exist, generate it."""
    config_file = Path(location)
    if not config_file.exists():
        config_file.write_text(DEFAULT_CONFIG)


def quote_message(message: str):
    """Quote a string in Discord format."""
    return '> ' + message.strip().replace('\n', '\n> ')


def user_string(user: User | Member) -> str:
    """Given a `User` or `Member`, return a string containing the user's name, discriminator, and user ID."""
    return f'{user.name}#{user.discriminator} ({user.id})'


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
