from pathlib import Path
from typing import Any, Dict

import aiosqlite

MIGRATIONS_DIR = Path(__file__).parent / 'migrations'
MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)


async def do_migrations(db_file: Path, defaults: Dict[str, Any]) -> None:
    """Do the database migrations by creating all the tables and moving the default settings to the DefaultSettings
    table."""
    sql_scripts = [path.read_text() for path in MIGRATIONS_DIR.iterdir()]

    async with aiosqlite.connect(db_file) as con:
        for script in sql_scripts:
            await con.executescript(script)
        await con.execute('DELETE FROM DefaultSettings')
        await con.executemany('INSERT INTO DefaultSettings (k, v) VALUES (?, ?)', defaults.items())
        await con.commit()


class BaseStore:
    """The base storage class which is inherited by all classes that handle database interactions."""

    def __init__(self, db_file: Path):
        self.db_file = db_file

    async def get_default_setting(self, key: Any) -> Any:
        """Return the default setting for `key`."""
        async with aiosqlite.connect(self.db_file) as con:
            statement = 'SELECT v FROM DefaultSettings WHERE k=?'
            cur = await con.execute(statement, (key,))
            res = await cur.fetchone()
            res = res and res[0]
            return res

    async def get_setting(self, guild_id: int, key: Any) -> Any:
        """Return the server specific setting for `key` and the default setting for `key` if none exists."""
        async with aiosqlite.connect(self.db_file) as con:
            statement = """SELECT IFNULL(S.v, D.v)
                        FROM (SELECT * FROM Settings WHERE guild_id = ?) S
                        FULL JOIN DefaultSettings D ON S.k = D.k
                        WHERE ? IN (S.k, D.k)
                        """
            cur = await con.execute(statement, (guild_id, key))
            res = await cur.fetchone()
            res = res and res[0]
            return res

    async def set_setting(self, guild_id: int, key: Any, value: Any) -> None:
        """Set the server-specific setting for `key`."""
        async with aiosqlite.connect(self.db_file) as con:
            statement = 'INSERT OR REPLACE INTO Settings(guild_id, k, v) VALUES (?, ?, ?)'
            await con.execute(statement, (guild_id, key, value))
            await con.commit()


class CoreStore(BaseStore):
    """The storage class that handles database interaction relevant to the core functions of the bot."""

    def __init__(self, db_file: Path) -> None:
        super().__init__(db_file)

    async def get_command_prefix(self, guild_id: int) -> str:
        return await self.get_setting(guild_id, 'command_prefix')

    async def set_command_prefix(self, guild_id: int, command_prefix: str) -> None:
        await self.set_setting(guild_id, 'command_prefix', command_prefix)
