from pathlib import Path
from typing import Any, Dict
from typing import Type, Tuple, List, TypeVar

import aiosqlite

T = TypeVar('T')

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


class InvalidQueryTypeError(Exception):
    """Raised when an invalid query type is encountered."""
    pass


class BaseStore:
    """The base storage class which is inherited by all classes that handle database interactions."""

    def __init__(self, db_file: Path):
        self.db_file = db_file

    async def _execute_select(self, query: str, params: Tuple[int | str, ...] = None, object_type: Type[T] = None,
                              single_row: bool = False) -> List[T] | T:
        async with aiosqlite.connect(self.db_file) as con:
            con.row_factory = aiosqlite.Row
            cur = await con.cursor()
            await cur.execute(query, params)
            if single_row:
                row = await cur.fetchone()
                if object_type is None:
                    return row and row[0]
                elif object_type in (str, int, bool):
                    return row and object_type(row[0])
                else:
                    return object_type(**row)
            else:
                rows = await cur.fetchall()
                if object_type is None:
                    return [row[0] for row in rows]
                elif object_type in (str, int, bool):
                    return [object_type(row[0]) if row[0] is not None else None for row in rows]
                else:
                    return [object_type(**row) for row in rows]

    async def _execute_modifying_query(self, query: str, params: Tuple[int | str, ...] = None) -> int:
        async with aiosqlite.connect(self.db_file) as con:
            cur = await con.cursor()
            await cur.execute(query, params)
            await con.commit()
            return cur.rowcount, cur.lastrowid

    async def execute_query(
            self,
            query: str,
            params: Tuple[int | str, ...] = None,
            obj_type: Type[T] = None,
            single_row: bool = False
    ) -> List[T] | T | int:
        """Execute a database query.

        Args:
            query: The database query to be executed.
            params: A tuple of parameters for the query.
            obj_type: The type of object to map the query results to (optional). If this is not specified or `str` or `int` or `bool`, return only a single element per row.
            single_row: If `True`, the SELECT query will return a single row. If False, it will return a list of rows.

        Returns:
            The result of the SELECT statement or a tuple containing the number of rows affected and the last row id if the query is an INSERT, UPDATE, or DELETE query.

        Raises:
            InvalidQueryTypeError: If the query is not a SELECT, INSERT, UPDATE, or DELETE query.
        """
        if query.upper().startswith('SELECT'):
            return await self._execute_select(query, params, obj_type, single_row)
        elif query.upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
            return await self._execute_modifying_query(query, params)
        else:
            raise InvalidQueryTypeError('Invalid query type.')


class SettingsStore(BaseStore):
    """This storage class is inherited by all classes that handle settings-related database interactions."""

    def __init__(self, db_file: Path):
        super().__init__(db_file)

    async def get_default_setting(self, key: Any) -> Any:
        """Return the default setting for `key`."""
        query = 'SELECT v FROM DefaultSettings WHERE k=?'
        params = (key,)
        return await self.execute_query(query, params, single_row=True)

    async def get_setting(self, guild_id: int, key: Any) -> Any:
        """Return the server specific setting for `key` and the default setting for `key` if none exists."""
        query = """SELECT IFNULL(S.v, D.v)
                   FROM (SELECT * FROM Settings WHERE guild_id = ?) S
                   FULL JOIN DefaultSettings D ON S.k = D.k
                   WHERE ? IN (S.k, D.k)
                   """
        params = (guild_id, key)
        return await self.execute_query(query, params, single_row=True)

    async def set_setting(self, guild_id: int, key: Any, value: Any) -> None:
        """Set the server-specific setting for `key`."""
        query = 'INSERT OR REPLACE INTO Settings(guild_id, k, v) VALUES (?, ?, ?)'
        params = (guild_id, key, value)
        await self.execute_query(query, params)
