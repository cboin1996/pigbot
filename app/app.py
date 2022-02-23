import discord
import sys
from models import config
client = discord.Client()

@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))

@client.event
async def on_message(message):
    if message.author == client.user:
            return
    
    if message.content.startswith("$hello"):
        await message.channel.send('Oink')

def main():
    pigbot_config = config.loader()
    client.run(pigbot_config.token)

if __name__=="__main__":
    main()