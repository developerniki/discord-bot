CREATE TABLE IF NOT EXISTS Settings(
    server_id INTEGER,
    key VARCHAR(20),
    value VARCHAR(20),
    PRIMARY KEY (server_id, key)
);

CREATE TABLE IF NOT EXISTS DefaultSettings(
    key VARCHAR(20),
    value VARCHAR(20),
    PRIMARY KEY (key)
);

INSERT OR REPLACE INTO DefaultSettings(key, value) VALUES
    ('starboard_channel', NULL),
    ('starboard_emoji', '⭐');

CREATE TABLE IF NOT EXISTS Watchlist(
    server_id INTEGER,
    user_id INTEGER,
    PRIMARY KEY (server_id, user_id)
);

CREATE TABLE IF NOT EXISTS HiddenChannels(
    server_id INTEGER,
    user_or_role_id INTEGER,
    channel_id INTEGER,
    PRIMARY KEY (server_id, user_or_role_id, channel_id)
);
