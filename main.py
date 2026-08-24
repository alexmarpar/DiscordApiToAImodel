import os

import discord
from discord.ext import commands

from modules.ai import setup_ai
from modules.stats import setup_stats
from modules.economy import setup_economy

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True


client = commands.Bot(
    command_prefix="!",
    intents=intents
)

@client.event
async def on_ready():
    print(f"Bot conectado como {client.user}")

    await client.change_presence(
        activity=discord.Game(name="Jugando a Mario Kart")
    )


async def main():
    setup_ai(client)
    setup_stats(client)
    setup_economy(client)

    await client.start(TOKEN)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())