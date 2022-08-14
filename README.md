# pigbot

Discord bot playground written in python as practice for docker and python.

Author: Christian Boin

# Configuration

Note any env vars with a `None` default value are needed to run the server.

| Variable                             | Default     | Type      |
| ------------------------------------ | ----------- | --------- |
| PIGBOT_TOKEN                         |             | str       |
| PIGBOT_MINECRAFT_SERVER_IP           |             | str       |
| PIGBOT_DISCORD_CHANNELS              |             | List[str] |
| PIGBOT_FAILED_QUERY_LIMIT            | 3           | int       |
| PIGBOT_MINECRAFT_ADMIN_UNAME         |             | str       |
| PIGBOT_LOG_FAILED_QUERIES            | False       | bool      |
| PIGBOT_MINECRAFT_ENABLE              | True        | bool      |
| PIGBOT_MINECRAFT_ONLINE_CHECK_ENABLE | True        | bool      |
| DALLE_ENABLE                         | True        | bool      |
| PIGBOT_DALLE_IP                      | "localhost" | str       |
| PIGBOT_DALLE_PORT                    | int         | 8000      |

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

Using cpu:

```
task dev-cpu -w
```

Lint:

```
task lint
```
