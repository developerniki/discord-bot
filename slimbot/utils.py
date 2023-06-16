import html

import aiohttp
from aiohttp import ContentTypeError, ClientConnectorError
from discord import User, Member


def quote_message(message: str):
    """Quote a string in Discord format."""
    return '> ' + message.strip().replace('\n', '\n> ')


def user_string(user: User | Member) -> str:
    """Given a `User` or `Member`, return a string containing the user's name, discriminator, and user ID."""
    discriminator_str = f'#{user.discriminator}' if user.discriminator else ''
    return f'{user.name}{discriminator_str} ({user.id})'


def unix_seconds_from_discord_snowflake_id(snowflake_id: int) -> int:
    """Converts a Discord snowflake ID to a unix timestamp in seconds as described here:
    https://discord.com/developers/docs/reference#snowflakes"""
    discord_epoch = 1_420_070_400_000
    return ((snowflake_id >> 22) + discord_epoch) // 1_000


async def fetch_html_escaped_string_from_api(url: str, key: str, default: str, from_list: bool = False) -> str:
    """Fetch a string from some web API and HTML unescape it.

    Args:
        url: The URL to fetch.
        key: The key of the desired value.
        default: Returns this if the request failed or returned None or an empty string.
        from_list: Whether the content is wrapped in a list.

    Returns:
        str: The result the API returned but HTML unescaped.
             Returns `default` if the result is either `None`, empty, or not a string.
    """
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    resp = await resp.json()
                    if from_list:
                        resp = resp[0] or []
                    result = resp.get(key)
                else:
                    result = None
        except (ClientConnectorError, ContentTypeError):
            result = None

    if not isinstance(result, str) or not result:
        result = default

    # Unescape HTML entities like `&quot;`.
    result = html.unescape(result)

    return result
