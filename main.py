import discord
import requests
import os

TOKEN = os.getenv("DISCORD_TOKEN")
API_KEY = os.getenv("API_KEY")
PERSONALIDAD = os.getenv("PERSONALIDAD")

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

if len(message.content) > 200:
    await message.channel.send("Learn to resume, machine")
    return
    
def generar_respuesta(prompt):
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {API_KEY}"
        },
        json={
            "model": "mistralai/mistral-7b-instruct",
            "messages": [
                {"role": "system", "content": PERSONALIDAD},
                {"role": "user", "content": prompt}
            ]
        }
    )

    return response.json()["choices"][0]["message"]["content"]

@client.event
async def on_ready():
    print(f"Bot conectado como {client.user}")

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith("!ai"):
        respuesta = generar_respuesta(message.content)
        await message.channel.send(respuesta)

client.run(TOKEN)
