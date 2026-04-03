import discord
import requests
import os

TOKEN = os.getenv("DISCORD_TOKEN")
API_KEY = os.getenv("API_KEY")
PERSONALIDAD = os.getenv("PERSONALIDAD")

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
    
def generar_respuesta(prompt):
    personalidad = "Eres un bot gracioso, sarcástico y un poco troll."

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {API_KEY}"
        },
        json={
            "model": "qwen/qwen3.6-plus:free",
            "messages": [
                {"role": "system", "content": personalidad},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 200
        }
    )

    data = response.json()
    print(data)  # 🔥 MUY IMPORTANTE (ver logs en Railway)

    if "choices" not in data:
        return f"Error de IA: {data}"

    return data["choices"][0]["message"]["content"]

@client.event
async def on_ready():
    print(f"Bot conectado como {client.user}")
    await client.change_presence(
        activity=discord.Game(name="Jugando a Candy Crush")
    )

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith("!crispys"):
        respuesta = generar_respuesta(message.content)
        await message.channel.send(respuesta)

client.run(TOKEN)
