import disnake
from disnake.ext import commands
import sqlite3

# database stuff
with open('create_dbs.sql') as file:
    sql_script = file.read()
con = sqlite3.connect('data.sqlite')
cur = con.cursor()
cur.executescript(sql_script)
con.commit()

# initialize bot
with open('bot-token.txt') as file:
    bot_token = file.read()
bot = commands.InteractionBot()


@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')


@bot.slash_command(description='Responds with World')
async def hello(inter):
    await inter.response.send_message('World')

# start bot
bot.run(bot_token)
