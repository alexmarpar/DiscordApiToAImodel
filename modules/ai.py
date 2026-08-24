import os
import requests


API_KEY = os.getenv("API_KEY")
PERSONALIDAD = os.getenv("PERSONALIDAD")


def generar_respuesta(prompt):
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {API_KEY}"
        },
        json={
            "model": "openrouter/free",
            "messages": [
                {
                    "role": "system",
                    "content": PERSONALIDAD
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 200
        }
    )

    data = response.json()

    if "choices" not in data:
        return f"Error de IA: {data}"

    return data["choices"][0]["message"]["content"]


def setup_ai(client):

    @client.event
    async def on_message(message):

        if message.author == client.user:
            return

        if message.content.startswith("!crispys"):
            respuesta = generar_respuesta(message.content)
            await message.channel.send(respuesta)