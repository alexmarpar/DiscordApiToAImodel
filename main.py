import os
import discord
import google.generativeai as genai
from discord.ext import commands

# Configurar Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

# Configurar Discord
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'Bot listo como {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user: return
    if bot.user in message.mentions:
        response = model.generate_content(message.content)
        await message.reply(response.text)
    await bot.process_commands(message)

bot.run(os.getenv("DISCORD_TOKEN"))
