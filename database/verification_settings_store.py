from pathlib import Path

from database import SettingsStore


class VerificationSettingsStore(SettingsStore):
    """Handles database access with the `Settings` table for settings related to the verification system."""

    def __init__(self, db_file: Path) -> None:
        super().__init__(db_file)

    async def get_join_channel_id(self, guild_id: int) -> int:
        return await self.get_setting(guild_id, 'join_channel_id')

    async def set_join_channel_id(self, guild_id: int, channel_id: int) -> None:
        await self.set_setting(guild_id, 'join_channel_id', channel_id)

    async def get_join_message(self, guild_id: int) -> str:
        return await self.get_setting(guild_id, 'join_message')

    async def set_join_message(self, guild_id: int, message: str) -> None:
        await self.set_setting(guild_id, 'join_message', message)

    async def get_welcome_channel_id(self, guild_id: int) -> int:
        return await self.get_setting(guild_id, 'welcome_channel_id')

    async def set_welcome_channel_id(self, guild_id: int, channel_id: int) -> None:
        await self.set_setting(guild_id, 'welcome_channel_id', channel_id)

    async def get_welcome_message(self, guild_id: int) -> str:
        return await self.get_setting(guild_id, 'welcome_message')

    async def set_welcome_message(self, guild_id: int, message: str) -> None:
        await self.set_setting(guild_id, 'welcome_message', message)

    async def get_request_channel_id(self, guild_id: int) -> int:
        return await self.get_setting(guild_id, 'verification_request_channel_id')

    async def set_request_channel_id(self, guild_id: int, channel_id: int) -> None:
        await self.set_setting(guild_id, 'verification_request_channel_id', channel_id)

    async def get_verification_role_id(self, guild_id: int) -> int:
        return await self.get_setting(guild_id, 'verification_role_id')

    async def set_verification_role_id(self, guild_id: int, role_id: int) -> None:
        await self.set_setting(guild_id, 'verification_role_id', role_id)

    async def get_adult_role_id(self, guild_id: int) -> int:
        return await self.get_setting(guild_id, 'adult_role_id')

    async def set_adult_role_id(self, guild_id: int, role_id: int) -> None:
        await self.set_setting(guild_id, 'adult_role_id', role_id)
