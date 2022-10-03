import disnake
from disnake.ext import commands
import sqlite3

# database stuff
con = sqlite3.connect('data.db')
cur = con.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS settings(key, server, value)')
data = [
    ('starboard-channel', None, None),
]
cur.executemany('INSERT OR IGNORE INTO settings VALUES(?, ?, ?)', data)
con.commit()

# initialize bot
with open('bot-token.txt') as file:
    bot_token = file.read()
bot = commands.InteractionBot()

# commands start here
@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')


@bot.slash_command(description='Responds with World')
async def hello(inter):
    await inter.response.send_message('World')

# run bot
if __name__ == '__main__':
    bot.run(bot_token)
