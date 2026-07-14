# Huey Deployment

Remaining steps to get the Huey queue working for issue #65.

## Manual Test

Do a manual test locally with some ZMF in place:
    uv run python manage.py sync_wiki

DONE: I added ZMF to a wiki page, added that wiki page to my character Zoltan in the development copy of the database, ran the above sync_wiki command. It reported success. I reloaded the page in the running dev app, and the fields in question were picked up.

## Prepare for deployment

Install the zingor-huey.service on the hosting VPS as /etc/systemd/system/zingor-huey.service

```
[Unit]
Description=Zingor Huey consumer (wiki sync)
After=network.target

[Service]
User=maxwell
WorkingDirectory=/home/maxwell/zingor
ExecStart=/home/maxwell/zingor/.venv/bin/python manage.py run_huey
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Match User/paths to zingor.service (both now invoke the venv directly, like gunicorn). Then:

```
sudo systemctl daemon-reload && sudo systemctl enable --now zingor-huey.service
```

## Push the new code to remote

## Manually deploy the code

The updated deploy.sh restarts zingor-huey.service after the app restarts.

## Bootstrap Joey's character

Use the admin UI to create a Character owned by Joey’s user with name="Lexent Povarov" and wiki_url="https://adventure.alexissmolensk.com/index.php/Lexent".

## Notify Joey to add microformats

He can add them, or I can do it for him.
