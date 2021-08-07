import json
import logging
import os
import signal
import sys
import time

import pickledb
import requests
import twitch

TWITCH_POLL_INTERVAL = os.environ.get("TWITCH_API_INTERVAL", 30)
TWITCH_ERROR_INTERVAL = os.environ.get("TWITCH_ERROR_INTERVAL", 60)
STREAM_OFFLINE_DELAY = os.environ.get("STREAM_OFFLINE_DELAY", 600)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
signal.signal(signal.SIGINT, lambda *args: sys.exit(0))

with open("data/streamers.json") as f:
    streamers = json.load(f)

db = pickledb.load("data/pickle.db", True)

discord_session = requests.Session()
# HACK: Use same session for twitch
twitch_session = requests.Session()
requests.Session = lambda: twitch_session

helix = twitch.Helix(
    os.environ.get("TWITCH_CLIENT_ID"), os.environ.get("TWITCH_CLIENT_SECRET")
)


def create_webhook(url, webhook):
    return discord_session.post(url, json=webhook, params={"wait": True})


def edit_webhook(url, message_id, webhook):
    return discord_session.patch(f"{url}/messages/{message_id}", json=webhook)


def edit_was_live(user_login, streamer):
    webhook = {"content": streamer["was_live_message"], "embeds": []}
    try:
        edit_webhook(streamer["webhook_url"], db[user_login]["message_id"], webhook)
    except:
        logging.warning("Webhook edit failed")


def get_webhook(user_login, streamer, stream):
    return {
        "content": streamer["now_live_message"],
        "embeds": [
            {
                "title": stream.title,
                "color": 0x6441A4,
                "timestamp": stream.data["started_at"],
                "url": f"https://twitch.tv/{user_login}",
                "image": {
                    "url": stream.thumbnail_url.replace("{width}", "426").replace(
                        "{height}", "240"
                    )
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


def update_webhooks(streams):
    for user_login, streamer in streamers.items():
        if user_login in streams:
            stream = streams[user_login]
            started_at = stream.data["started_at"]
            webhook = get_webhook(user_login, streamer, stream)

            if db.exists(user_login) and started_at != db[user_login]["started_at"]:
                if (
                    db.dexists(user_login, "ended_at")
                    and time.time() - db[user_login]["ended_at"] <= STREAM_OFFLINE_DELAY
                ):
                    logging.info("%s | STREAM RECOVERED", user_login)
                    db.dadd(user_login, ("started_at", started_at))
                else:
                    logging.info("%s | NEW STREAM", user_login)
                    edit_was_live(user_login, streamer)
                    del db[user_login]

            if db.exists(user_login):
                logging.info("%s | STILL LIVE", user_login)
                db.dpop(user_login, "ended_at")
                try:
                    response = edit_webhook(
                        streamer["webhook_url"], db[user_login]["message_id"], webhook
                    )
                    if response.status_code == 404:
                        logging.warning("Webhook not found")
                        del db[user_login]
                except:
                    logging.warning("Webhook edit failed")
            if not db.exists(user_login):
                logging.info("%s | NOW LIVE", user_login)
                try:
                    response = create_webhook(streamer["webhook_url"], webhook)
                    message_id = response.json()["id"]
                    db[user_login] = {
                        "message_id": message_id,
                        "started_at": started_at,
                    }
                    logging.info("%s | CREATED WEBHOOK '%s'", user_login, message_id)
                except:
                    logging.warning("Webhook create failed")
        elif db.exists(user_login):
            if db.dexists(user_login, "ended_at"):
                if time.time() - db[user_login]["ended_at"] > STREAM_OFFLINE_DELAY:
                    logging.info("%s | OFFLINE", user_login)
                    del db[user_login]
            else:
                logging.info("%s | WAS LIVE", user_login)
                db.dadd(user_login, ("ended_at", time.time()))
                edit_was_live(user_login, streamer)


logging.info("Now running")

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
        logging.warning("Get streams failed")
        time.sleep(TWITCH_ERROR_INTERVAL)
        continue

    update_webhooks(streams)

    time.sleep(TWITCH_POLL_INTERVAL)
