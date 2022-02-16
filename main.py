import functools
import logging
import os
import signal
import sys
import time

import pickledb
import requests
import twitchAPI
import yaml

TWITCH_POLL_INTERVAL = os.environ.get("TWITCH_API_INTERVAL", 30)
STREAM_OFFLINE_DELAY = os.environ.get("STREAM_OFFLINE_DELAY", 600)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
signal.signal(signal.SIGINT, lambda *args: sys.exit(0))

with open("data/streamers.yaml") as f:
    streamers = yaml.safe_load(f)

db = pickledb.load("data/pickle.db", True)

my_session = requests.Session()
# HACK: Force connection and read timeout for session
my_session.request = functools.partial(my_session.request, timeout=5)
# HACK: Use same session for twitch
requests.Session = lambda: my_session

twitch = twitchAPI.Twitch(
    os.environ.get("TWITCH_CLIENT_ID"), os.environ.get("TWITCH_CLIENT_SECRET")
)

def create_webhook(url, webhook):
    return my_session.post(url, json=webhook, params={"wait": True})


def edit_webhook(url, message_id, webhook):
    return my_session.patch(f"{url}/messages/{message_id}", json=webhook)


def edit_was_live(user_login):
    webhook = {"content": streamers[user_login]["was_live_message"], "embeds": []}
    try:
        edit_webhook(
            streamers[user_login]["webhook_url"], db[user_login]["message_id"], webhook
        )
    except:
        logging.warning("Webhook edit failed")


def get_webhook(user_login, stream):
    return {
        "content": streamers[user_login]["now_live_message"],
        "embeds": [
            {
                "title": stream["title"],
                "color": 0x6441A4,
                "timestamp": stream["started_at"],
                "url": f"https://twitch.tv/{user_login}",
                "image": {
                    "url": stream["thumbnail_url"]
                    .replace("{width}", "426")
                    .replace("{height}", "240")
                    + "?time="
                    + str(int(time.time() // 600))
                },
                "fields": [
                    {
                        "name": ":busts_in_silhouette: Viewers",
                        "value": stream["viewer_count"],
                        "inline": True,
                    },
                    {
                        "name": ":joystick: Category",
                        "value": stream["game_name"],
                        "inline": True,
                    },
                ],
            }
        ],
    }


def now_live(user_login, started_at, webhook):
    logging.info("%s | NOW LIVE", user_login)
    try:
        response = create_webhook(streamers[user_login]["webhook_url"], webhook)
        message_id = response.json()["id"]
        db[user_login] = {
            "message_id": message_id,
            "started_at": started_at,
        }
        logging.info("%s | CREATED WEBHOOK '%s'", user_login, message_id)
    except:
        logging.warning("Webhook create failed")


def still_live(user_login, webhook):
    logging.info("%s | STILL LIVE", user_login)
    try:
        response = edit_webhook(
            streamers[user_login]["webhook_url"], db[user_login]["message_id"], webhook
        )
        if response.status_code == 404:
            logging.warning("Webhook not found")
            del db[user_login]
    except:
        logging.warning("Webhook edit failed")


def update_webhooks(streams):
    for user_login in streamers:
        if user_login in streams:
            stream = streams[user_login]
            started_at = stream["started_at"]
            webhook = get_webhook(user_login, stream)

            if db.exists(user_login):
                if db.dexists(user_login, "ended_at"):
                    ended_at = db.dpop(user_login, "ended_at")
                    if time.time() - ended_at <= STREAM_OFFLINE_DELAY:
                        logging.info("%s | STREAM RECOVERED", user_login)
                        still_live(user_login, webhook)
                        return
                else:
                    still_live(user_login, webhook)
            else:
                now_live(user_login, started_at, webhook)
        elif db.exists(user_login):
            if db.dexists(user_login, "ended_at"):
                if time.time() - db[user_login]["ended_at"] > STREAM_OFFLINE_DELAY:
                    logging.info("%s | OFFLINE", user_login)
                    del db[user_login]
            else:
                logging.info("%s | WAS LIVE", user_login)
                edit_was_live(user_login)
                db.dadd(user_login, ("ended_at", time.time()))


user_logins = list(streamers.keys())

logging.info("Now running")

while True:
    streams = {
        stream["user_login"]: stream
        for stream in twitch.get_streams(user_login=user_logins)["data"]
    }
    update_webhooks(streams)
    time.sleep(TWITCH_POLL_INTERVAL)
