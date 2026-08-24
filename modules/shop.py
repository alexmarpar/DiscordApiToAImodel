import os
import aiosqlite
import discord

from discord import app_commands
from discord.ext import commands


# ============================================================
# CONFIG
# ============================================================

DB = os.getenv("ECONOMY_DB", "economy.db")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

SERVER_SYMBOL = os.getenv("CURRENCY_SYMBOL", "🪙")

if GUILD_ID == 0:
    raise RuntimeError("GUILD_ID no está definido")


# ============================================================
# SHOP COG
# ============================================================

class Shop(commands.Cog):
    """
    Sistema de tienda de Crispys.

    Base de datos:
        economy.db

    Tablas creadas:

        shop_items
        inventory
        economy_balances
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ========================================================
    # DATABASE
    # ========================================================

    async def init_db(self):
        async with aiosqlite.connect(DB) as db:

            await db.execute("""
                CREATE TABLE IF NOT EXISTS shop_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT DEFAULT '',
                    price INTEGER NOT NULL CHECK(price >= 0),
                    stock INTEGER DEFAULT -1,
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

            await db.execute("""
                CREATE TABLE IF NOT EXISTS economy_balances (
                    user_id INTEGER PRIMARY KEY,
                    balance INTEGER NOT NULL DEFAULT 0
                )
            """)

            await db.commit()

        print("[SHOP] Base de datos preparada")

    # ========================================================
    # BALANCE
    # ========================================================

    async def get_balance(self, user_id: int) -> int:
        async with aiosqlite.connect(DB) as db:

            cursor = await db.execute(
                """
                SELECT balance
                FROM economy_balances
                WHERE user_id = ?
                """,
                (user_id,)
            )

            row = await cursor.fetchone()

            if row is None:
                await db.execute(
                    """
                    INSERT INTO economy_balances
                    (user_id, balance)
                    VALUES (?, 0)
                    """,
                    (user_id,)
                )

                await db.commit()

                return 0

            return row[0]

    # ========================================================
    # SHOP
    # ========================================================

    @app_commands.command(
        name="shop",
        description="Muestra los objetos disponibles en la tienda."
    )
    async def shop_command(self, interaction: discord.Interaction):

        async with aiosqlite.connect(DB) as db:

            cursor = await db.execute("""
                SELECT
                    id,
                    name,
                    description,
                    price,
                    stock
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
            description="Objetos disponibles para comprar.",
            color=discord.Color.gold()
        )

        for item_id, name, description, price, stock in items:

            if stock == -1:
                stock_text = "♾️ Ilimitado"
            else:
                stock_text = f"📦 {stock}"

            embed.add_field(
                name=f"#{item_id} • {name}",
                value=(
                    f"{description or 'Sin descripción'}\n"
                    f"💰 **{price:,} {SERVER_SYMBOL}**\n"
                    f"{stock_text}"
                ),
                inline=False
            )

        embed.set_footer(
            text="Usa /buy para comprar un objeto."
        )

        await interaction.response.send_message(embed=embed)

    # ========================================================
    # BUY
    # ========================================================

    @app_commands.command(
        name="buy",
        description="Compra un objeto de la tienda."
    )
    @app_commands.describe(
        item="Nombre exacto del objeto que quieres comprar",
        quantity="Cantidad que quieres comprar"
    )
    async def buy_command(
        self,
        interaction: discord.Interaction,
        item: str,
        quantity: app_commands.Range[int, 1, 100]
    ):

        user_id = interaction.user.id

        async with aiosqlite.connect(DB) as db:

            await db.execute("BEGIN IMMEDIATE")

            # -----------------------------------------------
            # Buscar objeto
            # -----------------------------------------------

            cursor = await db.execute(
                """
                SELECT id, name, description, price, stock, role_id
                FROM shop_items
                WHERE LOWER(name) = LOWER(?)
                """,
                (item,)
            )

            shop_item = await cursor.fetchone()

            if shop_item is None:
                await db.rollback()

                await interaction.response.send_message(
                    f"❌ No existe ningún objeto llamado **{item}**.",
                    ephemeral=True
                )
                return

            item_id, name, description, price, stock, role_id = shop_item

            # -----------------------------------------------
            # Stock
            # -----------------------------------------------

            if stock != -1 and stock < quantity:

                await db.rollback()

                await interaction.response.send_message(
                    f"❌ No hay suficiente stock.\n"
                    f"Disponible: **{stock}**",
                    ephemeral=True
                )
                return

            # -----------------------------------------------
            # Saldo
            # -----------------------------------------------

            cursor = await db.execute(
                """
                SELECT balance
                FROM economy_balances
                WHERE user_id = ?
                """,
                (user_id,)
            )

            balance_row = await cursor.fetchone()

            if balance_row is None:

                balance = 0

                await db.execute(
                    """
                    INSERT INTO economy_balances
                    (user_id, balance)
                    VALUES (?, 0)
                    """,
                    (user_id,)
                )

            else:
                balance = balance_row[0]

            total_price = price * quantity

            if balance < total_price:

                await db.rollback()

                await interaction.response.send_message(
                    f"❌ No tienes suficiente dinero.\n\n"
                    f"Precio: **{total_price:,} {SERVER_SYMBOL}**\n"
                    f"Tu saldo: **{balance:,} {SERVER_SYMBOL}**",
                    ephemeral=True
                )
                return

            # -----------------------------------------------
            # Restar dinero
            # -----------------------------------------------

            await db.execute(
                """
                UPDATE economy_balances
                SET balance = balance - ?
                WHERE user_id = ?
                """,
                (total_price, user_id)
            )

            # -----------------------------------------------
            # Actualizar stock
            # -----------------------------------------------

            if stock != -1:

                await db.execute(
                    """
                    UPDATE shop_items
                    SET stock = stock - ?
                    WHERE id = ?
                    """,
                    (quantity, item_id)
                )

            # -----------------------------------------------
            # Añadir al inventario
            # -----------------------------------------------

            await db.execute(
                """
                INSERT INTO inventory
                (user_id, item_id, quantity)
                VALUES (?, ?, ?)

                ON CONFLICT(user_id, item_id)
                DO UPDATE SET
                    quantity = quantity + excluded.quantity
                """,
                (user_id, item_id, quantity)
            )

            await db.commit()

        # -----------------------------------------------
        # Dar rol si corresponde
        # -----------------------------------------------

        if role_id is not None:

            role = interaction.guild.get_role(role_id)

            if role is not None:

                try:
                    await interaction.user.add_roles(role)
                except discord.Forbidden:
                    pass

        new_balance = balance - total_price

        await interaction.response.send_message(
            f"✅ Has comprado **{quantity}x {name}**.\n\n"
            f"💰 Has pagado: **{total_price:,} {SERVER_SYMBOL}**\n"
            f"💳 Saldo restante: **{new_balance:,} {SERVER_SYMBOL}**"
        )

    # ========================================================
    # INVENTORY
    # ========================================================

    @app_commands.command(
        name="inventory",
        description="Muestra tu inventario."
    )
    async def inventory_command(
        self,
        interaction: discord.Interaction
    ):

        user_id = interaction.user.id

        async with aiosqlite.connect(DB) as db:

            cursor = await db.execute(
                """
                SELECT
                    s.name,
                    s.description,
                    i.quantity
                FROM inventory i

                INNER JOIN shop_items s
                    ON s.id = i.item_id

                WHERE i.user_id = ?
                  AND i.quantity > 0

                ORDER BY s.name
                """,
                (user_id,)
            )

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

    # ========================================================
    # ADD ITEM
    # ========================================================

    @app_commands.command(
        name="shop_add",
        description="Añade un objeto a la tienda."
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        name="Nombre del objeto",
        price="Precio",
        description="Descripción del objeto",
        stock="Stock (-1 = ilimitado)",
        role_id="ID del rol que se dará al comprarlo"
    )
    async def shop_add(
        self,
        interaction: discord.Interaction,
        name: str,
        price: app_commands.Range[int, 0, 2_000_000_000],
        description: str = "",
        stock: int = -1,
        role_id: str = None
    ):

        if stock < -1:

            await interaction.response.send_message(
                "❌ El stock debe ser `-1` o un número positivo.",
                ephemeral=True
            )
            return

        parsed_role_id = None

        if role_id:

            try:
                parsed_role_id = int(role_id)
            except ValueError:

                await interaction.response.send_message(
                    "❌ El ID del rol no es válido.",
                    ephemeral=True
                )
                return

        async with aiosqlite.connect(DB) as db:

            try:

                await db.execute(
                    """
                    INSERT INTO shop_items
                    (
                        name,
                        description,
                        price,
                        stock,
                        role_id
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        name,
                        description,
                        price,
                        stock,
                        parsed_role_id
                    )
                )

                await db.commit()

            except aiosqlite.IntegrityError:

                await interaction.response.send_message(
                    "❌ Ya existe un objeto con ese nombre.",
                    ephemeral=True
                )
                return

        await interaction.response.send_message(
            f"✅ Objeto **{name}** añadido a la tienda.\n"
            f"💰 Precio: **{price:,} {SERVER_SYMBOL}**"
        )

    # ========================================================
    # REMOVE ITEM
    # ========================================================

    @app_commands.command(
        name="shop_remove",
        description="Elimina un objeto de la tienda."
    )
    @app_commands.default_permissions(administrator=True)
    async def shop_remove(
        self,
        interaction: discord.Interaction,
        item: str
    ):

        async with aiosqlite.connect(DB) as db:

            cursor = await db.execute(
                """
                SELECT id, name
                FROM shop_items
                WHERE LOWER(name) = LOWER(?)
                """,
                (item,)
            )

            row = await cursor.fetchone()

            if row is None:

                await interaction.response.send_message(
                    "❌ Ese objeto no existe.",
                    ephemeral=True
                )
                return

            item_id, name = row

            await db.execute(
                """
                DELETE FROM shop_items
                WHERE id = ?
                """,
                (item_id,)
            )

            await db.commit()

        await interaction.response.send_message(
            f"🗑️ Objeto **{name}** eliminado."
        )

    # ========================================================
    # EDIT ITEM
    # ========================================================

    @app_commands.command(
        name="shop_edit",
        description="Edita un objeto de la tienda."
    )
    @app_commands.default_permissions(administrator=True)
    async def shop_edit(
        self,
        interaction: discord.Interaction,
        item: str,
        price: int = None,
        stock: int = None,
        description: str = None
    ):

        if price is None and stock is None and description is None:

            await interaction.response.send_message(
                "❌ Debes especificar algo que modificar.",
                ephemeral=True
            )
            return

        async with aiosqlite.connect(DB) as db:

            cursor = await db.execute(
                """
                SELECT id
                FROM shop_items
                WHERE LOWER(name) = LOWER(?)
                """,
                (item,)
            )

            row = await cursor.fetchone()

            if row is None:

                await interaction.response.send_message(
                    "❌ Ese objeto no existe.",
                    ephemeral=True
                )
                return

            item_id = row[0]

            updates = []
            values = []

            if price is not None:

                if price < 0:

                    await interaction.response.send_message(
                        "❌ El precio no puede ser negativo.",
                        ephemeral=True
                    )
                    return

                updates.append("price = ?")
                values.append(price)

            if stock is not None:

                if stock < -1:

                    await interaction.response.send_message(
                        "❌ El stock debe ser `-1` o positivo.",
                        ephemeral=True
                    )
                    return

                updates.append("stock = ?")
                values.append(stock)

            if description is not None:

                updates.append("description = ?")
                values.append(description)

            values.append(item_id)

            await db.execute(
                f"""
                UPDATE shop_items
                SET {", ".join(updates)}
                WHERE id = ?
                """,
                values
            )

            await db.commit()

        await interaction.response.send_message(
            f"✅ **{item}** actualizado correctamente."
        )


# ============================================================
# SETUP
# ============================================================

async def setup_shop(bot: commands.Bot):
    cog = Shop(bot)

    await cog.init_db()
    await bot.add_cog(cog)

    print("[SHOP] Módulo Shop cargado")