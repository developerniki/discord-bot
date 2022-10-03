CREATE TABLE IF NOT EXISTS settings(key, server, value);
CREATE TABLE IF NOT EXISTS watchlist(user, server);
INSERT OR IGNORE INTO settings
VALUES
    ('starboard-channel', NULL, NULL),
    ('watchlist-channel', NULL, NULL);
