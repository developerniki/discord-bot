import sqlite3

import disnake
from disnake import PartialEmoji, Guild, TextChannel
from disnake.ext import commands

from dbhelper import DbHelper


class DiscordBot(commands.InteractionBot):
    db = DbHelper()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


# Initialize the bot.
intents = disnake.Intents.default()
intents.reactions = True
bot = DiscordBot(intents=intents)


@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}.')


@bot.event
async def on_raw_reaction_add(payload):
    if payload.emoji.name == await bot.db.get_setting(payload.guild_id, 'starboard_emoji'):
        print('yep')


@bot.slash_command(description='Get starboard channel')
async def get_starboard_channel(inter):
    starboard_channel = await bot.db.get_setting(inter.guild.id, 'starboard_channel')
    await inter.response.send_message(starboard_channel)


@bot.slash_command(description='Set starboard channel')
async def set_starboard_channel(inter, channel: TextChannel):
    await bot.db.set_setting(inter.guild.id, 'starboard_channel', channel.id)
    await inter.response.send_message('Updated the starboard channel!')


@bot.slash_command(description='Get starboard emoji')
async def get_starboard_emoji(inter):
    starboard_emoji = await bot.db.get_setting(inter.guild.id, 'starboard_emoji')
    await inter.response.send_message(starboard_emoji)


@bot.slash_command(description='Set starboard emoji')
async def set_starboard_emoji(inter, emoji: str):
    await bot.db.set_setting(inter.guild.id, 'starboard_emoji', emoji)
    await inter.response.send_message('Updated the starboard emoji!')

if __name__ == '__main__':
    with open('bot-token.txt') as file:
        bot_token = file.read()

    # Run the bot.
    bot.run(bot_token)
