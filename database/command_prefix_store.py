from pathlib import Path

from database import SettingStore


class CommandPrefixStore(SettingStore):
    """The storage class that handles database interaction relevant to the core functions of the bot."""

    def __init__(self, db_file: Path) -> None:
        super().__init__(db_file)

    async def get_command_prefix(self, guild_id: int) -> str:
        return await self.get_setting(guild_id, 'command_prefix')

    async def set_command_prefix(self, guild_id: int, command_prefix: str) -> None:
        await self.set_setting(guild_id, 'command_prefix', command_prefix)
