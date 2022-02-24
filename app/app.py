import discord
import sys
from models import config
from cli import talk
client = discord.Client()

@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))

@client.event
async def on_message(message):
    if message.author == client.user:
            return
    
    response = talk.parse(message.content)
    await message.channel.send(response)

def main():
    pigbot_config = config.loader()
    client.run(pigbot_config.pigbot_token)

if __name__=="__main__":
    main()