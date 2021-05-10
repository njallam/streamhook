import json
import os
import shelve
import signal
import sys
import time
import twitch
from datetime import datetime
from discord_webhook import DiscordEmbed, DiscordWebhook
from dotenv import load_dotenv

signal.signal(signal.SIGINT, lambda *args: sys.exit(0))

load_dotenv()

with open("streamers.json") as f:
    streamers = json.load(f)

db = shelve.open("shelve.db")

helix = twitch.Helix(os.environ.get("TWITCH_CLIENT_ID"), os.environ.get("TWITCH_CLIENT_SECRET"))

while True:
    streams = {
        stream.data["user_login"]: stream
        for stream in helix.streams(user_login=streamers.keys())
    }

    for k, v in streamers.items():
        if k in streams.keys():
            stream = streams[k]
            stream_url = f"https://twitch.tv/{k}"
            webhook = DiscordWebhook(
                url=v["webhook_url"], content=v["now_live_message"]
            )
            preview_image = stream.thumbnail_url.replace("{width}", "426").replace(
                "{height}", "240"
            )
            started_at = stream.data["started_at"]
            embed = DiscordEmbed(title=stream.title, color="6441a4", timestamp=stream.data["started_at"], url=stream_url)
            embed.set_image(url=preview_image)
            embed.add_embed_field(
                name=":busts_in_silhouette: Viewers",
                value=stream.viewer_count,
                inline=True,
            )
            embed.add_embed_field(
                name=":joystick: Category", value=stream.data["game_name"], inline=True
            )
            webhook.add_embed(embed)
            if k in db.keys() and started_at == db[k]["started_at"]:
                print(f"{k} | STILL LIVE")
                try:
                    response = webhook.edit(db[k]["sent_webhook"])
                    if response.status_code == 404:
                        del db[k]
                except:
                    print("Webhook edit failed")
            if k not in db.keys():
                print(f"{k} | NOW LIVE")
                if k in db.keys() and "sent_webhook" in db[k]:
                    edit_was_live(k, v)
                try:
                    response = webhook.execute()
                    db[k] = {"sent_webhook": response, "started_at": started_at}
                except:
                    print("Webhook create failed")
        else:
            if k in db.keys() and "sent_webhook" in db[k]:
                print(f"{k} | WAS LIVE")
                edit_was_live(k, v)
    time.sleep(30)

def edit_was_live(user_login, streamer):
    webhook = DiscordWebhook(
        url=streamer["webhook_url"], content=streamer["was_live_message"]
    )
    try:
        webhook.update(db[user_login]["sent_webhook"])
        del db[user_login]
    except:
        print("Webhook edit failed")