import sqlite3

import aiosqlite


class DbHelper:
    def __init__(self, dbname='data.sqlite') -> None:
        self.dbname = dbname
        con = sqlite3.connect(dbname)
        cur = con.cursor()
        with open('create_dbs.sql') as file:
            sql_script = file.read()
            cur.executescript(sql_script)

    async def get_setting(self, server_id, key):
        async with aiosqlite.connect(self.dbname) as con:
            statement = 'SELECT value FROM Settings WHERE server_id=? AND key=?'
            cur = await con.execute(statement, (server_id, key))
            value = await cur.fetchone()

            if value is None:  # If the value has not been set, fetch the default.
                statement = 'SELECT value FROM DefaultSettings WHERE key=?'
                cur = await con.execute(statement, (key, ))
                value = await cur.fetchone()

            if value is not None:
                value = value[0]

            return value

    async def set_setting(self, server_id, key, value):
        async with aiosqlite.connect(self.dbname) as con:
            statement = 'INSERT OR REPLACE INTO Settings(server_id, key, value) VALUES (?, ?, ?)'
            await con.execute(statement, (server_id, key, value))
            await con.commit()


async def main():
    dbhelper = DbHelper()
    await dbhelper.get_setting(24323412, 'starboard_channel')
    await dbhelper.get_setting(24323412, 'starboard_emoji')
    await dbhelper.set_setting(24323412, 'starboard_channel', 4545343232)
    await dbhelper.get_setting(24323412, 'starboard_channel')


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
