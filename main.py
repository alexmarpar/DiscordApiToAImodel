import os
import asyncio

import discord
from discord.ext import commands

from modules.ai import setup_ai
from modules.stats import setup_stats
from modules.economy import setup_economy
from modules.shop import setup_shop

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN no está definido")

if GUILD_ID == 0:
    raise RuntimeError("GUILD_ID no está definido")

GUILD = discord.Object(id=GUILD_ID)



intents = discord.Intents.default()

intents.message_content = True
intents.members = True
intents.voice_states = True
intents.presences = True



client = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# READY
# ============================================================

@client.event
async def on_ready():

    print("=" * 60)

    print(
        f"Bot conectado como {client.user}",
        flush=True
    )

    print(
        f"[BOT] ID: {client.user.id}",
        flush=True
    )

    # --------------------------------------------------------
    # PRESENCIA
    # --------------------------------------------------------

    await client.change_presence(
        activity=discord.Game(
            name="Jugando a Mario Kart"
        )
    )

    # --------------------------------------------------------
    # SLASH COMMANDS
    # --------------------------------------------------------

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


# ============================================================
# MAIN
# ============================================================

async def main():

    print(
        "[MAIN] Registrando módulos...",
        flush=True
    )

    setup_ai(client)
    setup_stats(client)
    setup_economy(client)
    await setup_shop(client)

    print(
        "[MAIN] Módulos registrados correctamente",
        flush=True
    )


    await client.start(TOKEN)



if __name__ == "__main__":

    asyncio.run(main())