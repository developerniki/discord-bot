CREATE TABLE IF NOT EXISTS DefaultSettings(
    k PRIMARY KEY,
    v
);

CREATE TABLE IF NOT EXISTS Settings(
    guild_id BIGINT NOT NULL,
    k NOT NULL,
    v,
    PRIMARY KEY (guild_id, k)
);

CREATE TABLE IF NOT EXISTS Tickets(
    id INTEGER PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    reason VARCHAR,
    status VARCHAR CHECK (status IN ("open", "closed")),
    channel_id BIGINT,
    log VARCHAR, -- store JSON data in here
    created_at BIGINT,
    closed_at BIGINT
);

CREATE TABLE IF NOT EXISTS TicketRequests(
    id INTEGER PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    ticket_id INTEGER,
    reason VARCHAR,
    status VARCHAR CHECK (status IN ("pending", "accepted", "rejected")),
    channel_id BIGINT,
    created_at BIGINT,
    closed_at BIGINT,
    FOREIGN KEY (ticket_id) REFERENCES Tickets(id) ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS UserTicketCooldowns(
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    ticket_id INTEGER, -- `null` if created manually
    cooldown_ends_at INTEGER NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES Tickets(id) ON UPDATE CASCADE ON DELETE CASCADE
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS VerificationRequests(
    id INTEGER PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    join_channel_id BIGINT NOT NULL,
    join_message_id BIGINT NOT NULL,
    verified BOOLEAN NOT NULL CHECK (verified IN (FALSE, TRUE)),
    joined_at BIGINT NOT NULL,
    closed_at BIGINT,
    age VARCHAR,
    gender VARCHAR,
);
