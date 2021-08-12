# Streamhook

Twitch livestream notifications in Discord using webhooks

## Configuration

1. Set environment variables:
    1. Replace `your_twitch_client_id` and `your_twitch_client_secret` with your Twitch client ID and secret from the [Twitch developer console](https://dev.twitch.tv/console/apps).
```sh
TWITCH_CLIENT_ID=your_twitch_client_id
TWITCH_CLIENT_SECRET=your_twitch_client_secret
```
3. Write streamer configuration in `data/streamers.json`.  Specify multiple streamers by adding additional dictionary entries.
    1. Replace `twitch_username` with the lower case Twitch username you want to monitor.
    2. Replace `discord_webhook_url` with a webhook URL for the channel to post the webhook.  
    3. Replace `role_id` with the id of the role to ping.  Alternatively you could ping a user or remove the mention entirely.
```json
{
    "twitch_username": {
        "webhook_url": "discord_webhook_url",
        "now_live_message": "<@&role_id> Stream is live!!",
        "was_live_message": "Stream was live.."
    }
}
```

## Docker (Compose)

```yaml
version: '3'
services:
  streamhook:
    image: ghcr.io/njallam/streamhook
    container_name: streamhook
    restart: unless-stopped
    volumes:
      - "./streamhook:/app/data" # Create streamers.json as above
    environment:
      - TWITCH_CLIENT_ID=your_twitch_client_id
      - TWITCH_CLIENT_SECRET=your_twitch_client_secret
```
