# yt-cast

Converts YouTube channels to podcasts. Removes ads with SponsorBlock.

## Environment Variables

ROCKET_base_url - base url to include in feeds
ROCKET_channel_whitelist - array of whitelisted channel names. TOML syntax.

## Caveats

It's not well tested and not something intended for public usage. For example, it only lets you access whitelisted channels.

I made this for my own usage, so it's not very configurable. Some things I remember that are hardcoded:
- cache time
- delay before including videos in feed
