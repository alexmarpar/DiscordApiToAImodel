import os
import aiosqlite
import discord

from discord import app_commands
from discord.ext import commands


DB = os.getenv("ECONOMY_DB", "economy.db")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
SERVER_SYMBOL = os.getenv("SERVER_SYMBOL", "🪙")

if GUILD_ID == 0:
    raise RuntimeError("GUILD_ID no está definido")


class Shop(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def init_db(self):

        async with aiosqlite.connect(DB) as db:

            await db.execute("""
                CREATE TABLE IF NOT EXISTS shop_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT DEFAULT '',
                    price INTEGER NOT NULL DEFAULT 0,
                    stock INTEGER NOT NULL DEFAULT -1,
                    role_id INTEGER DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    user_id INTEGER NOT NULL,
                    item_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,

                    PRIMARY KEY (user_id, item_id),

                    FOREIGN KEY (item_id)
                        REFERENCES shop_items(id)
                        ON DELETE CASCADE
                )
            """)

            await db.commit()

        print("[SHOP] Base de datos lista")

    # =========================================================
    # /shop
    # =========================================================

    @app_commands.command(
        name="shop",
        description="Muestra la tienda."
    )
    async def shop(self, interaction: discord.Interaction):

        async with aiosqlite.connect(DB) as db:

            cursor = await db.execute("""
                SELECT id, name, description, price, stock
                FROM shop_items
                ORDER BY price ASC
            """)

            items = await cursor.fetchall()

        if not items:

            await interaction.response.send_message(
                "🛒 La tienda está vacía.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🛒 Tienda",
            description="Objetos disponibles",
            color=discord.Color.gold()
        )

        for item_id, name, description, price, stock in items:

            stock_text = (
                "♾️ Ilimitado"
                if stock == -1
                else f"📦 {stock}"
            )

            embed.add_field(
                name=f"#{item_id} • {name}",
                value=(
                    f"{description or 'Sin descripción'}\n"
                    f"💰 **{price:,} {SERVER_SYMBOL}**\n"
                    f"{stock_text}"
                ),
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    # =========================================================
    # /buy
    # =========================================================

    @app_commands.command(
        name="buy",
        description="Compra un objeto de la tienda."
    )
    @app_commands.describe(
        item="Nombre del objeto",
        quantity="Cantidad"
    )
    async def buy(
        self,
        interaction: discord.Interaction,
        item: str,
        quantity: app_commands.Range[int, 1, 100]
    ):

        async with aiosqlite.connect(DB) as db:

            cursor = await db.execute("""
                SELECT id, name, price, stock
                FROM shop_items
                WHERE LOWER(name) = LOWER(?)
            """, (item,))

            row = await cursor.fetchone()

            if row is None:

                await interaction.response.send_message(
                    "❌ Ese objeto no existe.",
                    ephemeral=True
                )
                return

            item_id, name, price, stock = row

            if stock != -1 and stock < quantity:

                await interaction.response.send_message(
                    f"❌ No hay suficiente stock.\n"
                    f"Disponible: **{stock}**",
                    ephemeral=True
                )
                return

            total = price * quantity

            # -------------------------------------------------
            # Buscar saldo de economy.py
            # -------------------------------------------------

            cursor = await db.execute("""
                SELECT balance
                FROM economy_balances
                WHERE user_id = ?
            """, (interaction.user.id,))

            balance_row = await cursor.fetchone()

            if balance_row is None:

                await interaction.response.send_message(
                    "❌ No tienes cuenta económica.",
                    ephemeral=True
                )
                return

            balance = balance_row[0]

            if balance < total:

                await interaction.response.send_message(
                    f"❌ No tienes suficiente dinero.\n\n"
                    f"Precio: **{total:,} {SERVER_SYMBOL}**\n"
                    f"Saldo: **{balance:,} {SERVER_SYMBOL}**",
                    ephemeral=True
                )
                return

            # -------------------------------------------------
            # Restar dinero
            # -------------------------------------------------

            await db.execute("""
                UPDATE economy_balances
                SET balance = balance - ?
                WHERE user_id = ?
            """, (
                total,
                interaction.user.id
            ))

            # -------------------------------------------------
            # Stock
            # -------------------------------------------------

            if stock != -1:

                await db.execute("""
                    UPDATE shop_items
                    SET stock = stock - ?
                    WHERE id = ?
                """, (
                    quantity,
                    item_id
                ))

            # -------------------------------------------------
            # Inventario
            # -------------------------------------------------

            await db.execute("""
                INSERT INTO inventory
                (
                    user_id,
                    item_id,
                    quantity
                )
                VALUES (?, ?, ?)

                ON CONFLICT(user_id, item_id)
                DO UPDATE SET
                    quantity = quantity + excluded.quantity
            """, (
                interaction.user.id,
                item_id,
                quantity
            ))

            await db.commit()

        await interaction.response.send_message(
            f"✅ Has comprado **{quantity}x {name}**.\n"
            f"💰 Precio: **{total:,} {SERVER_SYMBOL}**"
        )

    # =========================================================
    # /inventory
    # =========================================================

    @app_commands.command(
        name="inventory",
        description="Muestra tu inventario."
    )
    async def inventory(self, interaction: discord.Interaction):

        async with aiosqlite.connect(DB) as db:

            cursor = await db.execute("""
                SELECT
                    s.name,
                    s.description,
                    i.quantity
                FROM inventory i

                JOIN shop_items s
                    ON s.id = i.item_id

                WHERE i.user_id = ?
                  AND i.quantity > 0

                ORDER BY s.name
            """, (interaction.user.id,))

            items = await cursor.fetchall()

        if not items:

            await interaction.response.send_message(
                "🎒 Tu inventario está vacío.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"🎒 Inventario de {interaction.user.display_name}",
            color=discord.Color.blue()
        )

        for name, description, quantity in items:

            embed.add_field(
                name=f"📦 {name} × {quantity}",
                value=description or "Sin descripción",
                inline=False
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


# =============================================================
# SETUP
# =============================================================

async def setup_shop(bot: commands.Bot):

    shop = Shop(bot)

    await shop.init_db()

    await bot.add_cog(shop)

    # ---------------------------------------------------------
    # SINCRONIZAR COMANDOS
    # ---------------------------------------------------------

    guild = discord.Object(id=GUILD_ID)

    synced = await bot.tree.sync(guild=guild)

    print(
        f"[SHOP] Módulo cargado")