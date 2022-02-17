import functools
import json
import logging
import os
import signal
import sys
import time

import requests
import twitchAPI
import yaml

TWITCH_POLL_INTERVAL = os.environ.get("TWITCH_API_INTERVAL", 30)
STREAM_OFFLINE_DELAY = os.environ.get("STREAM_OFFLINE_DELAY", 600)

logging.basicConfig(format="%(levelname)s - %(message)s", level=logging.INFO)
signal.signal(signal.SIGINT, lambda *args: sys.exit(0))

with open("data/streamers.yaml") as f:
    streamers = yaml.safe_load(f)

db = json.load(open("data/pickle.db"))

my_session = requests.Session()
# HACK: Force connection and read timeout for session
my_session.request = functools.partial(my_session.request, timeout=5)
# HACK: Use same session for twitch
requests.Session = lambda: my_session

twitch = twitchAPI.Twitch(
    os.environ.get("TWITCH_CLIENT_ID"), os.environ.get("TWITCH_CLIENT_SECRET")
)


def save_db():
    json.dump(db, open("data/pickle.db", "w"))


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
    try:
        response = edit_webhook(
            streamers[user_login]["webhook_url"], db[user_login]["message_id"], webhook
        )
        if response.status_code == 404:
            logging.warning("Webhook not found")
            del db[user_login]
            save_db()
    except:
        logging.warning("Webhook edit failed")


def update_webhooks(streams):
    for user_login in streamers:
        if user_login in streams:
            stream = streams[user_login]
            started_at = stream["started_at"]
            webhook = get_webhook(user_login, stream)
            if user_login in db:
                if "ended_at" in db[user_login]:
                    ended_at = db[user_login]["ended_at"]
                    del db[user_login]["ended_at"]
                    if time.time() - ended_at <= STREAM_OFFLINE_DELAY:
                        logging.info("%s | STREAM RECOVERED", user_login)
                        still_live(user_login, webhook)
                    else:
                        logging.info("%s | NEW STREAM", user_login)
                        edit_was_live(user_login)
                        now_live(user_login, started_at, webhook)
                    save_db()
                else:
                    logging.info("%s | STILL LIVE", user_login)
                    still_live(user_login, webhook)
            else:
                logging.info("%s | NOW LIVE", user_login)
                now_live(user_login, started_at, webhook)
                save_db()
        elif user_login in db:
            if "ended_at" in db[user_login]:
                if time.time() - db[user_login]["ended_at"] > STREAM_OFFLINE_DELAY:
                    logging.info("%s | OFFLINE", user_login)
                    del db[user_login]
                    save_db()
            else:
                logging.info("%s | WAS LIVE", user_login)
                edit_was_live(user_login)
                db[user_login]["ended_at"] = time.time()
                save_db()


user_logins = list(streamers.keys())

logging.info("Now running")

while True:
    streams = {
        stream["user_login"]: stream
        for stream in twitch.get_streams(user_login=user_logins)["data"]
    }
    update_webhooks(streams)
    time.sleep(TWITCH_POLL_INTERVAL)
