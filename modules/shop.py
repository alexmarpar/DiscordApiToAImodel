# modules/shop.py

import os
from datetime import datetime, timezone

import aiosqlite
import discord


# ============================================================
# CONFIG
# ============================================================

DB = os.getenv(
    "ECONOMY_DB",
    "economy.db"
)

GUILD_ID = int(
    os.getenv("GUILD_ID", "0")
)

if GUILD_ID == 0:
    raise RuntimeError(
        "GUILD_ID no está definido"
    )

GUILD = discord.Object(
    id=GUILD_ID
)


# ============================================================
# MONEDA
# ============================================================

CURRENCY_NAME = os.getenv(
    "CURRENCY_NAME",
    "Coins"
)

CURRENCY_SYMBOL = os.getenv(
    "CURRENCY_SYMBOL",
    "💰"
)


# ============================================================
# GLOBAL
# ============================================================

_client = None
_initialized = False


# ============================================================
# UTILIDADES
# ============================================================

def now():
    return datetime.now(timezone.utc)


def format_money(amount):
    return f"{CURRENCY_SYMBOL} {amount:,}"


# ============================================================
# DATABASE
# ============================================================

async def init_db():

    print(
        "[SHOP][DB] Inicializando...",
        flush=True
    )

    async with aiosqlite.connect(DB) as db:

        # ----------------------------------------------------
        # PRODUCTOS
        # ----------------------------------------------------

        await db.execute("""
            CREATE TABLE IF NOT EXISTS shop_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                name TEXT NOT NULL UNIQUE,

                description TEXT,

                price INTEGER NOT NULL,

                stock INTEGER NOT NULL DEFAULT -1,

                role_id INTEGER,

                created_at TEXT NOT NULL
            )
        """)

        # ----------------------------------------------------
        # INVENTARIO
        # ----------------------------------------------------

        await db.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                guild_id INTEGER NOT NULL,

                user_id INTEGER NOT NULL,

                item_id INTEGER NOT NULL,

                quantity INTEGER NOT NULL DEFAULT 0,

                created_at TEXT NOT NULL,

                updated_at TEXT NOT NULL,

                PRIMARY KEY (
                    guild_id,
                    user_id,
                    item_id
                ),

                FOREIGN KEY (
                    item_id
                )
                REFERENCES shop_items(id)
                ON DELETE CASCADE
            )
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_shop_items_name

            ON shop_items(name)
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_inventory_user

            ON inventory(
                guild_id,
                user_id
            )
        """)

        await db.commit()

    print(
        "[SHOP][DB] Base de datos lista",
        flush=True
    )


# ============================================================
# /SHOP
# ============================================================
async def shop_command(
    interaction: discord.Interaction
):

    print(
        "[SHOP] /shop ejecutado",
        flush=True
    )

    await interaction.response.send_message(
        "🛒 La tienda funciona correctamente."
    )
"""

async def shop_command(
    interaction: discord.Interaction
):

    if interaction.guild is None:

        await interaction.response.send_message(
            "❌ Este comando solo funciona en un servidor.",
            ephemeral=True
        )

        return

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
        description=(
            f"Compra objetos usando "
            f"{CURRENCY_SYMBOL} **{CURRENCY_NAME}**."
        ),
        color=discord.Color.gold(),
        timestamp=now()
    )

    for (
        item_id,
        name,
        description,
        price,
        stock
    ) in items:

        if stock == -1:
            stock_text = "♾️ Ilimitado"
        else:
            stock_text = f"📦 Stock: **{stock}**"

        embed.add_field(
            name=f"#{item_id} • {name}",
            value=(
                f"{description or 'Sin descripción'}\n"
                f"💰 **{format_money(price)}**\n"
                f"{stock_text}\n\n"
                f"Compra: `/buy {name}`"
            ),
            inline=False
        )

    embed.set_footer(
        text=f"Tienda de {interaction.guild.name}"
    )

    await interaction.response.send_message(
        embed=embed
    )

"""
# ============================================================
# /BUY
# ============================================================

async def buy_command(
    interaction: discord.Interaction,
    item: str,
    quantity: int = 1
):

    if interaction.guild is None:

        await interaction.response.send_message(
            "❌ Este comando solo funciona en un servidor.",
            ephemeral=True
        )

        return

    if quantity <= 0:

        await interaction.response.send_message(
            "❌ La cantidad debe ser mayor que 0.",
            ephemeral=True
        )

        return

    if quantity > 100:

        await interaction.response.send_message(
            "❌ No puedes comprar más de 100 unidades de una vez.",
            ephemeral=True
        )

        return

    guild_id = interaction.guild.id
    user_id = interaction.user.id

    async with aiosqlite.connect(DB) as db:

        # ----------------------------------------------------
        # TRANSACTION
        # ----------------------------------------------------

        await db.execute(
            "BEGIN IMMEDIATE"
        )

        # ----------------------------------------------------
        # PRODUCTO
        # ----------------------------------------------------

        cursor = await db.execute("""
            SELECT
                id,
                name,
                description,
                price,
                stock,
                role_id
            FROM shop_items

            WHERE LOWER(name) = LOWER(?)
        """, (item,))

        shop_item = await cursor.fetchone()

        if shop_item is None:

            await db.rollback()

            await interaction.response.send_message(
                f"❌ No existe el objeto **{item}**.",
                ephemeral=True
            )

            return

        (
            item_id,
            item_name,
            description,
            price,
            stock,
            role_id
        ) = shop_item

        # ----------------------------------------------------
        # STOCK
        # ----------------------------------------------------

        if stock != -1 and stock < quantity:

            await db.rollback()

            await interaction.response.send_message(
                f"❌ No hay suficiente stock.\n"
                f"Disponible: **{stock}**.",
                ephemeral=True
            )

            return

        # ----------------------------------------------------
        # CUENTA
        # ----------------------------------------------------

        cursor = await db.execute("""
            SELECT balance
            FROM accounts

            WHERE guild_id = ?
            AND user_id = ?
        """, (
            guild_id,
            user_id
        ))

        account = await cursor.fetchone()

        if account is None:

            await db.rollback()

            await interaction.response.send_message(
                "❌ No tienes una cuenta económica.",
                ephemeral=True
            )

            return

        balance = account[0]

        # ----------------------------------------------------
        # PRECIO
        # ----------------------------------------------------

        total_price = price * quantity

        if balance < total_price:

            await db.rollback()

            await interaction.response.send_message(
                "❌ No tienes suficiente dinero.\n\n"
                f"💰 Precio: **{format_money(total_price)}**\n"
                f"💳 Tu saldo: **{format_money(balance)}**",
                ephemeral=True
            )

            return

        current = now().isoformat()

        # ----------------------------------------------------
        # RESTAR DINERO
        # ----------------------------------------------------

        await db.execute("""
            UPDATE accounts

            SET
                balance = balance - ?,
                updated_at = ?

            WHERE guild_id = ?
            AND user_id = ?
        """, (
            total_price,
            current,
            guild_id,
            user_id
        ))

        # ----------------------------------------------------
        # TRANSACCIÓN ECONÓMICA
        # ----------------------------------------------------

        await db.execute("""
            INSERT INTO transactions (
                guild_id,

                from_user_id,
                to_user_id,

                amount,

                type,

                description,

                timestamp
            )

            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            guild_id,

            user_id,
            None,

            total_price,

            "shop",

            f"Compra: {quantity}x {item_name}",

            current
        ))

        # ----------------------------------------------------
        # STOCK
        # ----------------------------------------------------

        if stock != -1:

            await db.execute("""
                UPDATE shop_items

                SET stock = stock - ?

                WHERE id = ?
            """, (
                quantity,
                item_id
            ))

        # ----------------------------------------------------
        # INVENTARIO
        # ----------------------------------------------------

        await db.execute("""
            INSERT INTO inventory (
                guild_id,
                user_id,
                item_id,
                quantity,
                created_at,
                updated_at
            )

            VALUES (?, ?, ?, ?, ?, ?)

            ON CONFLICT (
                guild_id,
                user_id,
                item_id
            )

            DO UPDATE SET
                quantity =
                    inventory.quantity
                    + excluded.quantity,

                updated_at =
                    excluded.updated_at
        """, (
            guild_id,
            user_id,
            item_id,
            quantity,
            current,
            current
        ))

        await db.commit()

    # --------------------------------------------------------
    # ROL
    # --------------------------------------------------------

    if role_id:

        role = interaction.guild.get_role(
            role_id
        )

        if role:

            try:

                await interaction.user.add_roles(
                    role,
                    reason=f"Compra en tienda: {item_name}"
                )

            except discord.Forbidden:

                pass

    # --------------------------------------------------------
    # RESPUESTA
    # --------------------------------------------------------

    new_balance = balance - total_price

    embed = discord.Embed(
        title="🛒 Compra realizada",
        color=discord.Color.green(),
        timestamp=now()
    )

    embed.add_field(
        name="📦 Producto",
        value=f"{item_name} × {quantity}",
        inline=False
    )

    embed.add_field(
        name="💸 Precio",
        value=format_money(total_price),
        inline=True
    )

    embed.add_field(
        name="💰 Saldo restante",
        value=format_money(new_balance),
        inline=True
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# /INVENTORY
# ============================================================
async def inventory_command(
    interaction: discord.Interaction,
    user: discord.Member = None
):

    if interaction.guild is None:

        await interaction.response.send_message(
            "❌ Este comando solo funciona en un servidor.",
            ephemeral=True
        )

        return

    # Si no especifica usuario, muestra el suyo
    if user is None:
        user = interaction.user

    if user.bot:

        await interaction.response.send_message(
            "❌ Los bots no tienen inventario.",
            ephemeral=True
        )

        return

    async with aiosqlite.connect(DB) as db:

        cursor = await db.execute("""
            SELECT
                s.name,
                s.description,
                i.quantity

            FROM inventory i

            INNER JOIN shop_items s
                ON s.id = i.item_id

            WHERE i.guild_id = ?
            AND i.user_id = ?
            AND i.quantity > 0

            ORDER BY s.name ASC
        """, (
            interaction.guild.id,
            user.id
        ))

        items = await cursor.fetchall()

    # --------------------------------------------------------
    # SIN INVENTARIO
    # --------------------------------------------------------

    if not items:

        await interaction.response.send_message(
            f"🎒 **{user.display_name}** no tiene objetos.",
            ephemeral=True
        )

        return

    # --------------------------------------------------------
    # EMBED
    # --------------------------------------------------------

    embed = discord.Embed(
        title="🎒 Inventario",
        description=(
            f"Inventario de **{user.display_name}**"
        ),
        color=discord.Color.blue(),
        timestamp=now()
    )

    embed.set_thumbnail(
        url=user.display_avatar.url
    )

    for (
        name,
        description,
        quantity
    ) in items:

        embed.add_field(
            name=f"📦 {name} × {quantity}",
            value=description or "Sin descripción",
            inline=False
        )

    embed.set_footer(
        text=f"ID: {user.id}"
    )

    await interaction.response.send_message(
        embed=embed
    )
# ============================================================
# /SHOPINFO
# ============================================================

async def shop_info_command(
    interaction: discord.Interaction
):

    async with aiosqlite.connect(DB) as db:

        cursor = await db.execute("""
            SELECT COUNT(*)
            FROM shop_items
        """)

        result = await cursor.fetchone()

    item_count = result[0]

    embed = discord.Embed(
        title="🛒 Información de la tienda",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="💰 Moneda",
        value=(
            f"{CURRENCY_SYMBOL} "
            f"{CURRENCY_NAME}"
        ),
        inline=True
    )

    embed.add_field(
        name="📦 Productos",
        value=str(item_count),
        inline=True
    )

    await interaction.response.send_message(
        embed=embed
    )
# ============================================================
# ADMIN CHECK
# ============================================================

def is_admin(interaction: discord.Interaction):

    return (
        interaction.guild is not None
        and interaction.user.guild_permissions.administrator
    )


# ============================================================
# /SHOP_ADD
# ============================================================

@discord.app_commands.default_permissions(administrator=True)
async def shop_add_command(
    interaction: discord.Interaction,
    name: str,
    price: int,
    description: str = "",
    stock: int = -1,
    role_id: str = ""
):

    if not is_admin(interaction):
        await interaction.response.send_message(
            "❌ Solo los administradores pueden utilizar este comando.",
            ephemeral=True
        )
        return

    if price < 0:

        await interaction.response.send_message(
            "❌ El precio no puede ser negativo.",
            ephemeral=True
        )

        return

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

        role = interaction.guild.get_role(
            parsed_role_id
        )

        if role is None:

            await interaction.response.send_message(
                "❌ No existe ese rol en el servidor.",
                ephemeral=True
            )

            return

    async with aiosqlite.connect(DB) as db:

        try:

            await db.execute(
                """
                INSERT INTO shop_items (
                    name,
                    description,
                    price,
                    stock,
                    role_id,
                    created_at
                )

                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    description,
                    price,
                    stock,
                    parsed_role_id,
                    now().isoformat()
                )
            )

            await db.commit()

        except aiosqlite.IntegrityError:

            await interaction.response.send_message(
                f"❌ Ya existe **{name}**.",
                ephemeral=True
            )

            return

    await interaction.response.send_message(
        f"✅ Producto **{name}** creado.\n"
        f"💰 Precio: **{format_money(price)}**"
    )


# ============================================================
# /SHOP_REMOVE
# ============================================================

@discord.app_commands.default_permissions(administrator=True)
async def shop_remove_command(
    interaction: discord.Interaction,
    name: str
):

    if not is_admin(interaction):
        await interaction.response.send_message(
            "❌ Solo los administradores pueden utilizar este comando.",
            ephemeral=True
        )
        return

    async with aiosqlite.connect(DB) as db:

        cursor = await db.execute(
            """
            SELECT id, name
            FROM shop_items

            WHERE LOWER(name) = LOWER(?)
            """,
            (name,)
        )

        item = await cursor.fetchone()

        if item is None:

            await interaction.response.send_message(
                f"❌ No existe **{name}**.",
                ephemeral=True
            )

            return

        item_id, item_name = item

        await db.execute(
            """
            DELETE FROM shop_items
            WHERE id = ?
            """,
            (item_id,)
        )

        await db.commit()

    await interaction.response.send_message(
        f"🗑️ Producto **{item_name}** eliminado."
    )


# ============================================================
# /SHOP_EDIT
# ============================================================

@discord.app_commands.default_permissions(administrator=True)
async def shop_edit_command(
    interaction: discord.Interaction,
    name: str,
    price: int = None,
    stock: int = None,
    description: str = None,
    role_id: str = None
):

    if not is_admin(interaction):

        await interaction.response.send_message(
            "❌ Solo los administradores pueden utilizar este comando.",
            ephemeral=True
        )

        return

    if price is not None and price < 0:

        await interaction.response.send_message(
            "❌ El precio no puede ser negativo.",
            ephemeral=True
        )

        return

    if stock is not None and stock < -1:

        await interaction.response.send_message(
            "❌ El stock debe ser `-1` o un número positivo.",
            ephemeral=True
        )

        return

    parsed_role_id = None

    if role_id is not None:

        if role_id == "":
            parsed_role_id = None

        else:

            try:
                parsed_role_id = int(role_id)

            except ValueError:

                await interaction.response.send_message(
                    "❌ El ID del rol no es válido.",
                    ephemeral=True
                )

                return

            if interaction.guild.get_role(
                parsed_role_id
            ) is None:

                await interaction.response.send_message(
                    "❌ No existe ese rol.",
                    ephemeral=True
                )

                return

    # --------------------------------------------------------
    # Construir UPDATE
    # --------------------------------------------------------

    updates = []
    values = []

    if price is not None:

        updates.append(
            "price = ?"
        )

        values.append(price)

    if stock is not None:

        updates.append(
            "stock = ?"
        )

        values.append(stock)

    if description is not None:

        updates.append(
            "description = ?"
        )

        values.append(description)

    if role_id is not None:

        updates.append(
            "role_id = ?"
        )

        values.append(parsed_role_id)

    if not updates:

        await interaction.response.send_message(
            "❌ No has indicado ningún cambio.",
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
            (name,)
        )

        item = await cursor.fetchone()

        if item is None:

            await interaction.response.send_message(
                f"❌ No existe **{name}**.",
                ephemeral=True
            )

            return

        item_id = item[0]

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
        f"✅ Producto **{name}** actualizado."
    )
# ============================================================
# READY
# ============================================================

async def shop_on_ready():

    global _initialized

    if _initialized:
        return

    print(
        "[SHOP] Inicializando módulo...",
        flush=True
    )

    await init_db()

    _initialized = True

    print(
        "[SHOP] Módulo listo",
        flush=True
    )


# ============================================================
# SETUP
# ============================================================

def setup_shop(client):

    global _client

    if _client is not None:

        print(
            "[SHOP] Módulo ya registrado",
            flush=True
        )

        return

    _client = client

    print(
        "[SHOP] Registrando módulo...",
        flush=True
    )

    # ========================================================
    # /SHOP
    # ========================================================

    client.tree.add_command(
        discord.app_commands.Command(
            name="shop",
            description="Muestra los productos de la tienda.",
            callback=shop_command
        ),
        guild=GUILD
    )

    # ========================================================
    # /BUY
    # ========================================================

    client.tree.add_command(
        discord.app_commands.Command(
            name="buy",
            description="Compra un producto de la tienda.",
            callback=buy_command
        ),
        guild=GUILD
    )

    # ========================================================
    # /INVENTORY
    # ========================================================

    client.tree.add_command(
        discord.app_commands.Command(
            name="inventory",
            description="Muestra tu inventario.",
            callback=inventory_command
        ),
        guild=GUILD
    )

    # ========================================================
    # /SHOPINFO
    # ========================================================

    client.tree.add_command(
        discord.app_commands.Command(
            name="shopinfo",
            description="Muestra información de la tienda.",
            callback=shop_info_command
        ),
        guild=GUILD
    )

    # ========================================================
    # ADMIN COMMANDS
    # ========================================================

    client.tree.add_command(
        discord.app_commands.Command(
            name="shop_add",
            description="Crea un producto en la tienda.",
            callback=shop_add_command
        ),
        guild=GUILD
    )

    client.tree.add_command(
        discord.app_commands.Command(
            name="shop_remove",
            description="Elimina un producto de la tienda.",
            callback=shop_remove_command,
        ),
        guild=GUILD
    )

    client.tree.add_command(
        discord.app_commands.Command(
            name="shop_edit",
            description="Edita un producto de la tienda.",
            callback=shop_edit_command,
        ),
        guild=GUILD
    )