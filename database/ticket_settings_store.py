from pathlib import Path

from database import SettingStore


class TicketSettingsStore(SettingStore):
    """Handles database access with the `Settings` table for settings related to the ticket system."""

    def __init__(self, db_file: Path) -> None:
        super().__init__(db_file)

    async def get_request_channel_id(self, guild_id: int) -> int:
        return await self.get_setting(guild_id, 'ticket_request_channel_id')

    async def set_request_channel_id(self, guild_id: int, channel_id: int) -> None:
        await self.set_setting(guild_id, 'ticket_request_channel_id', channel_id)

    async def get_log_channel_id(self, guild_id: int) -> int:
        return await self.get_setting(guild_id, 'ticket_log_channel_id')

    async def set_log_channel_id(self, guild_id: int, channel_id: int) -> None:
        await self.set_setting(guild_id, 'ticket_log_channel_id', channel_id)

    async def get_guild_cooldown(self, guild_id: int) -> int:
        return await self.get_setting(guild_id, 'ticket_cooldown')

    async def set_guild_cooldown(self, guild_id: int, cooldown_in_secs: int) -> None:
        return await self.set_setting(guild_id, 'ticket_cooldown', cooldown_in_secs)
