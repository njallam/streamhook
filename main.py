import json
import os
import requests
import shelve
import signal
import sys
import time
import twitch
from datetime import date, datetime

signal.signal(signal.SIGINT, lambda *args: sys.exit(0))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

with open("data/streamers.json") as f:
    streamers = json.load(f)

db = shelve.open("data/shelve.db")
discord_session = requests.Session()

# HACK: Use same session for twitch
twitch_session = requests.Session()
requests.Session = lambda: twitch_session

helix = twitch.Helix(
    os.environ.get("TWITCH_CLIENT_ID"), os.environ.get("TWITCH_CLIENT_SECRET")
)


def log(message):
    print(datetime.now(), "|", message)


def create_webhook(url, webhook):
    return discord_session.post(url, json=webhook, params={"wait": True})


def edit_webhook(url, id, webhook):
    return discord_session.patch(f"{url}/messages/{id}", json=webhook)


def edit_was_live(user_login, streamer):
    webhook = {"content": streamer["was_live_message"], "embeds": []}
    try:
        edit_webhook(streamer["webhook_url"], db[user_login]["message_id"], webhook)
        del db[user_login]
    except:
        log("Webhook edit failed")

log("Now running")

while True:
    streams = {}
    try:
        streams = {
            stream.data["user_login"]: stream
            for stream in helix.streams(user_login=streamers.keys())
        }
    except twitch.helix.resources.streams.StreamNotFound:
        pass
    except:
        log("Get streams failed")

    for user_login, streamer in streamers.items():
        if user_login in streams.keys():
            stream = streams[user_login]
            started_at = stream.data["started_at"]
            webhook = {
                "content": streamer["now_live_message"],
                "embeds": [
                    {
                        "title": stream.title,
                        "color": 0x6441A4,
                        "timestamp": started_at,
                        "url": f"https://twitch.tv/{user_login}",
                        "image": {
                            "url": stream.thumbnail_url.replace(
                                "{width}", "426"
                            ).replace("{height}", "240")
                        },
                        "fields": [
                            {
                                "name": ":busts_in_silhouette: Viewers",
                                "value": stream.viewer_count,
                                "inline": True,
                            },
                            {
                                "name": ":joystick: Category",
                                "value": stream.data["game_name"],
                                "inline": True,
                            },
                        ],
                    }
                ],
            }
            if user_login in db.keys() and started_at == db[user_login]["started_at"]:
                log(f"{user_login} | STILL LIVE")
                try:
                    response = edit_webhook(
                        streamer["webhook_url"], db[user_login]["message_id"], webhook
                    )
                    if response.status_code == 404:
                        log("Webhook not found")
                        del db[user_login]
                except:
                    log("Webhook edit failed")
            if user_login not in db.keys():
                log(f"{user_login} | NOW LIVE")
                if user_login in db.keys() and "message_id" in db[user_login]:
                    edit_was_live(user_login, streamer)
                try:
                    response = create_webhook(streamer["webhook_url"], webhook)
                    db[user_login] = {
                        "message_id": response.json()["id"],
                        "started_at": started_at,
                    }
                except:
                    log("Webhook create failed")
        else:
            if user_login in db.keys() and "message_id" in db[user_login]:
                log(f"{user_login} | WAS LIVE")
                edit_was_live(user_login, streamer)
    time.sleep(30)
