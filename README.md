# pigbot

Discord bot playground written in python as practice for docker and python.

# Features

- Dalle-mini interface compatible with fastAPI dalle server [dalle-ays](https://github.com/cboin1996/dalle-ays)
  - Image generation via text
  - Model downloading/loading of any dalle-mini and vqgan models
  - Image search
- Minecraft serverstatus updates:
  - Players joined/left detection
  - Server status
  - Automatic IP change detection
  - Notifications for server downtime

Author: Christian Boin

# Configuration

Note any env vars with a `None` default value are needed to run the server.

| Variable                                           | Default     | Type      | Description                                        |
| -------------------------------------------------- | ----------- | --------- | -------------------------------------------------- |
| PIGBOT_TOKEN                                       |             | str       | discord bot api token                              |
| PIGBOT_MINECRAFT_SERVER_IP                         |             | str       | ip of the minecraft server                         |
| PIGBOT_MINECRAFT_SERVER_PORT                       | 25565       | int       | port of the minecraft server                       |
| PIGBOT_DISCORD_CHANNELS                            |             | List[str] | channel ids to post messages too within the server |
| PIGBOT_FAILED_QUERY_LIMIT                          | 3           | int       | number of failed queries before notifying admin    |
| PIGBOT_MINECRAFT_ADMIN_UNAME                       |             | str       | admin dev username (copied as id from discord)     |
| PIGBOT_LOG_FAILED_QUERIES                          | False       | bool      | log failed queries to chat                         |
| PIGBOT_MINECRAFT_ENABLE                            | True        | bool      | enable minecraft api                               |
| PIGBOT_MINECRAFT_ONLINE_CHECK_ENABLE               | True        | bool      | enable checks for the server being online          |
| PIGBOT_MINECRAFT_LOCAL_SERVER_IP_DETECTION_ENABLED | False       | bool      | enable auto-detection of ip changes for the server |
| DALLE_ENABLE                                       | True        | bool      | enable dalle-ays api                               |
| PIGBOT_DALLE_IP                                    | "localhost" | str       | ip of dalle-ays server                             |
| PIGBOT_DALLE_PORT                                  | 8000        | int       | port of dalle-ays                                  |
| PIGBOT_DALLE_MAX_NUMBER_OF_IMAGES                  | 2           | int       | number of images to return by default for dalle    |

# Development

Mandatory env vars are required from the configuration section in a .env file!

To kickstart the creation of that file, run

```
task env
```

## Locally

Configure vscode debugger for live reload local build (you will need cuda and nvidia drivers):

```
{
  "configurations": [
    {
      "name": "Python: Pigbot",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": ["app.main:app", "--reload", "--log-level", "debug"],
      "jinja": true,
      "justMyCode": true,
      "envFile": "${workspaceFolder}/.env"
    },
  ]
}

```

## Docker

Or, alternatively,

Build the image:

```
task build
```

Run:

Using a gpu:

```
task run
```

Using cpu only

```
task run-cpu
```

Development (live reload docker builds with gpu):
Using gpu:

```
task dev -w
```

Lint:

```
task lint
```

## Configuring a custom bot with permissions

In discord developer portal, set the following under Oauth2 generator

- Scope
  - bot
  - applications.commands
- Bot Permissions
  - Read Messages/View Channels
  - Send Messages
  - Send Messages in Threads
  - Embed Links
  - Attach Files
  - Read Message History
  - Mention Everyone
  - Use Slash Commands
  - Connect
  - Speak
