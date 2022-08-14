version: "3"

output: prefixed
vars:
  APP_NAME: pigbot
  VERSION: v0.0.8
  APP_ROOT: app
tasks:
  setup:
    prefix: setup
    desc: sets up the development environment
    cmds:
      - 'python3 -m venv venv'
      - echo activate your venv with 'source venv/bin/activate'
    sources:
      - venv

  install-deps:
    prefix: install-deps
    cmds:
      - pip install --upgrade pip
      - pip install black isort
      - pip install -r {{.APP_ROOT}}/requirements.txt
      - pip install pydantic[dotenv]

  build:
    prefix: build
    desc: builds the docker app
    cmds:
      - docker build -t {{.APP_NAME}}:{{.VERSION}} .

  clean:
    prefix: clean
    desc: removes the built image
    cmds:
      - docker rm {{.APP_NAME}} || true

  stop:
    prefix: stop
    desc: stops the running container
    cmds:
      - docker kill {{.APP_NAME}}

  dev:
    prefix: dev
    desc: runs the app with gpu (use -w flag for live rebuilds)
    cmds:
      - task: clean
      - task: build
      - task: run
    sources:
      - '{{.APP_ROOT}}/**'
      - '{{.APP_ROOT}}/*/**'
      - Dockerfile

  lint:
    prefix: lint
    desc: lint the application
    cmds:
      - black {{.APP_ROOT}}/.
    deps: [setup]

  run:
    prefix: run
    cmds:
      - docker run --rm --name {{.APP_NAME}} -p 443:8443 --env-file .env -v "${PWD}":/{{.APP_ROOT}} {{.APP_NAME}}:{{.VERSION}} --log-level debug

  env:
    prefix: env
    cmds:
      - echo "PIGBOT_TOKEN=" >> .env
      - echo "PIGBOT_MINECRAFT_SERVER_IP=" >> .env
      - echo "PIGBOT_DISCORD_CHANNELS=[]" >> .env
      - echo "PIGBOT_FAILED_QUERY_LIMIT=3 >> .env
      - echo "PIGBOT_MINECRAFT_ADMIN_UNAME=" >> .env
      - echo "PIGBOT_LOG_FAILED_QUERIES=False" >> .env