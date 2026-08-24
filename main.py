import os
import asyncio
import discord

from modules.ai import setup_ai
from modules.stats import setup_stats
from modules.economy import setup_economy


TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

GUILD = discord.Object(id=GUILD_ID)


intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.presences = True


client = discord.Client(intents=intents)


@client.event
async def on_ready():

    print("=" * 60)
    print(f"Bot conectado como {client.user}", flush=True)


    await client.change_presence(
        activity=discord.Game(name="Jugando a Mario Kart")
    )

    try:

        synced = await client.tree.sync(
            guild=GUILD
        )

        print(
            f"[COMMANDS] {len(synced)} comandos sincronizados",
            flush=True
        )

        for command in synced:

            print(
                f"[COMMANDS] /{command.name}",
                flush=True
            )

    except Exception as e:

        print(
            f"[COMMANDS] ERROR: "
            f"{type(e).__name__}: {e}",
            flush=True
        )

    print("=" * 60)


async def main():

    print("[MAIN] Registrando módulos...", flush=True)

    setup_ai(client)
    setup_stats(client)
    setup_economy(client)

    print("[MAIN] Módulos registrados", flush=True)

    await client.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())