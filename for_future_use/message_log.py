import asyncio
import base64
import io
import json
import logging
import zipfile
from datetime import datetime
from typing import List, Dict, Any

from discord import Message

from database import Ticket
from slimbot import tools

_logger = logging.getLogger(__name__)


@staticmethod
def __log_body_as_dict_list(messages: List[Message], attachment_filenames: List[str],
                            attachment_conents: List[bytes]) -> List[Dict[str, Any]]:
    log_as_dict = [
        {
            'message_id': message.id,
            'author_id': message.author.id,
            'author_name': f'{message.author.name}#{message.author.discriminator}',
            'created_at': round(message.created_at.timestamp()),
            'message': message.content,
            'embeds': [embed.to_dict() for embed in message.embeds],
            'references': message.reference.message_id if message.reference else None,
            'reactions': [reaction.emoji for reaction in message.reactions],
            # TODO Do not save the attachment body itself in the database.
            # Instead, save to disk and only record the disk filename.
            'attachments': [{'filename': f, 'content': base64.b64encode(c).decode('utf-8')} for f, c in
                            zip(attachment_filenames, attachment_conents)]
        }
        for message in messages
    ]
    return log_as_dict


def __log_header_as_str(self, ticket: Ticket, time_fmt: str) -> str:
    created_at = datetime.fromtimestamp(ticket.created_at).strftime(time_fmt)
    closed_at = datetime.fromtimestamp(ticket.closed_at).strftime(time_fmt)

    ticket_user = self.bot.get_user(ticket.user_id)
    header = f'Transcript of ticket #{ticket.id}, created at {created_at} for ' \
             f'user {tools.user_string(ticket_user)}'
    if ticket.reason:
        header += f' with reason "{ticket.reason}" '
    header += f'and closed at {closed_at}\n'
    return header


@staticmethod
def __log_body_as_str(messages: List[Message], time_fmt: str) -> str:
    body_as_list = []
    for message in messages:
        created_at = message.created_at.strftime(time_fmt)
        author = tools.user_string(message.author)
        content = message.content.strip()
        embeds = [json.dumps(embed.to_dict(), separators=(',', ':')) for embed in message.embeds]
        embeds = '\n'.join(embeds)
        cur_line = f'[{created_at}] {author}: {content}'
        if embeds:
            cur_line += f'\n{embeds}'
        body_as_list.append(cur_line)
    body_as_str = '\n'.join(body_as_list)
    return body_as_str


def __log_as_str(self, ticket: Ticket, messages: List[Message], time_fmt: str) -> str:
    return self.__log_header_as_str(ticket, time_fmt) + self.__log_body_as_str(messages, time_fmt)


@staticmethod
def __zip_files_into_buffer(buffer, filenames, contents):
    with zipfile.ZipFile(buffer, mode='w', compression=zipfile.ZIP_DEFLATED, allowZip64=False,
                         compresslevel=9) as zip_file:
        for i, (filename, content) in enumerate(zip(filenames, contents)):
            zip_file.writestr(filename, content)
    buffer.seek(0)


async def __attachments_as_zip_file(self, attachment_filenames: List[str],
                                    attachment_contents: List[bytes]) -> io.BytesIO:
    # TODO Proably need to do this in a new loop.
    zip_buffer = io.BytesIO()
    loop = asyncio.get_running_loop()
    task = loop.run_in_executor(
        None,
        self.__zip_files_into_buffer,
        zip_buffer,
        attachment_filenames,
        attachment_contents
    )
    await task

    # TODO Split zip file if it is larger than 8 MB.

    return zip_buffer


# Retrieve the attachments.
attachment_contents: List[bytes] = []
attachment_filenames: List[str] = []
for m in messages:
    for a in m.attachments:
        if a:
            try:
                attachment_contents.append(await a.read())
                attachment_filenames.append(a.filename)
            except (HTTPException, Forbidden, NotFound) as e:
                _logger.exception('Error while trying to retrieve attachment.')
                pass



            # Retrieve the relevant ticket and channel history.
            ticket = await self.ticket_store.get_ticket_by_channel_id(ctx.channel.id)
            messages: List[Message] = [message async for message in ctx.channel.history(limit=None, oldest_first=True)]

            # Close the ticket and store the decision to close the ticket and the log in the database.
            log_as_dict = self.__log_body_as_dict_list(messages, attachment_filenames, attachment_contents)
            await self.ticket_store.close(ticket=ticket, log=json.dumps(log_as_dict))

            # If a log channel exists, store the log there.
            ticket_log_channel_id = await self.ticket_settings_store.get_log_channel_id(ctx.guild.id)
            ticket_log_channel = ctx.guild.get_channel(ticket_log_channel_id)
            if ticket_log_channel is not None:
                filename_base = f'ticket_log_{ticket.id}'

                txt_filename = f'{filename_base}_transcript.txt'
                log_as_str = self.__log_as_str(ticket, messages, time_fmt='%Y-%m-%d %H:%M:%S')
                await ticket_log_channel.send(
                    content=txt_filename,
                    file=discord.File(fp=io.StringIO(log_as_str), filename=txt_filename),
                )

                if attachment_filenames:
                    zip_filename = f'{filename_base}_attachments.zip'
                    zipped_attachments = await self.__attachments_as_zip_file(attachment_filenames, attachment_contents)
                    await ticket_log_channel.send(
                        content=zip_filename,
                        file=discord.File(fp=zipped_attachments, filename=zip_filename),
                    )
