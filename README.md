# discord-bot
A simple Discord bot with various moderation features.

# TODO

## Before bot is used publicly
- [ ] Ticket System
	- [ ] Auto-delete channels for closed tickets.
	- [ ] Implement ticket logging. Implement a command to retrieve the logged content for the ticket. At the same time, implement general logging (as it does not make sense to implement it just for the ticket system).
- [ ] Final TODOs.
	- [ ] Upload the bot to GitHub.
	- [ ] Through Discord's web interface, give the bot only the necessary permissions and intents.
	- [ ] Set up Docker and upload the project to a DigitalOcean droplet.
	- [ ] Test the bot thoroughly. -> With Andy.
- [x] Implement commands to ticket system:
	- [x] Make tickets manually.
	- [x] Add and remove users from a ticket.
	- [x] Allow closing all tickets for user.
- [x] Deactivate the `RandomButtonsView` from the `fun` extensions.
- [x] Test the echo command.
- [x] Check if multiple regexes can be executed at the same time.
- [x] Use emoji package.
- [x] Add a command to load, unload, and reload extensions.
- [x] Make it so the bot doesn't respond to other bots' messages.
- [x] Make the initial message of a new ticket an embed.
- [x] Add proper error handling (add exceptions where appropriate).
- [x] Add proper logging.
- [x] Test if the bot recurses when you tell it 'hi'.
- [x] Test if regexes from `fun_config.toml` work.

## General
- [x] Move `get_command_prefix` and `set_command_prefix` to `database.py`.
- [x] Document everything using [Python docstrings](https://peps.python.org/pep-0257/).
- [ ] Check if the bot reacts to buttons made by other bot. If yes, implement appropriate security measures.
- [ ] Implement everything from CandyCat's message.
- [ ] Write a help message for each command.

## Ticket System
- [ ] Change the ticket system to have two ticket categories:
	- Support Tickets
	- General Tickets
- [ ] Add ticket `opened_at`, `acknowledged_at`, and `closed_at` times.
- [ ] Notify users when the module goes offline.
- [ ] Use private threads when the server's boost level is high enough.
- [x] In the `closeTicket` method, check if this is a ticket in the first place and log the ticket using the database.
- [x] Don't allow making duplicate channels using `createTicketRequestButton`.
- [x] Apply a cooldown after a ticket was rejected.
- [x] Add the user ID in parentheses in the header of the embed.
- [x] Move `get_ticket_request_channel` and `set_ticket_request_channel` to `database.py`.
- [x] Change color of ticket request embed when accepted or rejected (yellow for accepted, red for rejected).

# Moderation
- [ ] Kick, ban, mute, etc. commands.

## Database
- [x] Put the functionality for every cog into its own file and class.
- [x] To improve decoupling, use IDs instead of objects in database classes. While it is generally preferable to use the entire object (compare Rust's newtype idiom), the latter in this case contains connection information that is not required for the database classes.
- [x] Put default values in config file.

## Other
- [x] Use command groups.
- [x] Use TOML rather than JSON for config file(s).
