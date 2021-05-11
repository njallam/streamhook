import json
import os
import requests
import shelve
import signal
import sys
import time
import twitch
from dotenv import load_dotenv

signal.signal(signal.SIGINT, lambda *args: sys.exit(0))

load_dotenv()

with open("streamers.json") as f:
    streamers = json.load(f)

db = shelve.open("shelve.db")
discord_session = requests.Session()

# HACK: Use same session for twitch
twitch_session = requests.Session()
requests.Session = lambda: twitch_session

helix = twitch.Helix(
    os.environ.get("TWITCH_CLIENT_ID"), os.environ.get("TWITCH_CLIENT_SECRET")
)


def create_webhook(url, webhook):
    return discord_session.post(url, json=webhook, params={"wait": True})


def edit_webhook(url, id, webhook):
    return discord_session.patch(f"{url}/messages/{id}", json=webhook)


def edit_was_live(user_login, streamer):
    webhook = {"content": streamer["was_live_message"], 'embeds':[]}
    try:
        edit_webhook(streamer["webhook_url"], db[k]["message_id"], webhook)
        del db[user_login]
    except:
        print("Webhook edit failed")


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
        print("Get streams failed")

    for k, v in streamers.items():
        if k in streams.keys():
            stream_url = f"https://twitch.tv/{k}"
            stream = streams[k]
            started_at = stream.data["started_at"]
            webhook = {
                "content": v["now_live_message"],
                "embeds": [
                    {
                        "title": stream.title,
                        "color": 0x6441a4,
                        "timestamp": started_at,
                        "url": stream_url,
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
            if k in db.keys() and started_at == db[k]["started_at"]:
                print(f"{k} | STILL LIVE")
                try:
                    response = edit_webhook(v["webhook_url"], db[k]["message_id"], webhook)
                    if response.status_code == 404:
                        del db[k]
                except:
                    print("Webhook edit failed")
            if k not in db.keys():
                print(f"{k} | NOW LIVE")
                if k in db.keys() and "message_id" in db[k]:
                    edit_was_live(k, v)
                try:
                    response = create_webhook(v["webhook_url"], webhook)
                    db[k] = {
                        "message_id": response.json()["id"],
                        "started_at": started_at,
                    }
                except:
                    print("Webhook create failed")
        else:
            if k in db.keys() and "message_id" in db[k]:
                print(f"{k} | WAS LIVE")
                edit_was_live(k, v)
    time.sleep(30)
