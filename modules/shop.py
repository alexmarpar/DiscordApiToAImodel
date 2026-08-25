import os
from datetime import datetime, timezone
from decimal import Decimal

import discord
from discord import app_commands
from psycopg_pool import AsyncConnectionPool


# ============================================================
# CONFIG
# ============================================================

DATABASE_URL = os.getenv("DATABASE_ECONOMY_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_ECONOMY_URL no está definido"
    )


GUILD_ID = int(
    os.getenv(
        "GUILD_ID",
        "0"
    )
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
_db_pool = None


# ============================================================
# UTILIDADES
# ============================================================

def now():
    return datetime.now(timezone.utc)


def format_money(amount):

    amount = Decimal(str(amount))

    return (
        f"{CURRENCY_SYMBOL} "
        f"{amount:,.2f}"
    )


# ============================================================
# DATABASE EXECUTE
# ============================================================

async def db_execute(
    query,
    params=(),
    fetch=False,
    fetchall=False
):

    if _db_pool is None:

        raise RuntimeError(
            "El pool de PostgreSQL no está inicializado"
        )

    async with _db_pool.connection() as conn:

        async with conn.transaction():

            async with conn.cursor() as cursor:

                await cursor.execute(
                    query,
                    params
                )

                if fetch:

                    return await cursor.fetchone()

                if fetchall:

                    return await cursor.fetchall()

                return None


# ============================================================
# DATABASE INIT
# ============================================================

async def init_db():

    global _db_pool

    print(
        "[SHOP][DB] Conectando a Neon...",
        flush=True
    )

    _db_pool = AsyncConnectionPool(
        conninfo=DATABASE_URL,
        min_size=1,
        max_size=5,
        open=False
    )

    await _db_pool.open()

    # ========================================================
    # TEST DE CONEXIÓN
    # ========================================================

    result = await db_execute(
        "SELECT 1",
        fetch=True
    )

    if result != (1,):

        raise RuntimeError(
            "La conexión con Neon no respondió correctamente"
        )

    print(
        "[SHOP][DB] Conectado a Neon",
        flush=True
    )

    # ========================================================
    # ACCOUNTS
    # ========================================================

    await db_execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (

            guild_id BIGINT NOT NULL,

            user_id BIGINT NOT NULL,

            balance NUMERIC(20, 2)
                NOT NULL
                DEFAULT 0
                CHECK (balance >= 0),

            created_at TIMESTAMPTZ
                NOT NULL
                DEFAULT NOW(),

            updated_at TIMESTAMPTZ
                NOT NULL
                DEFAULT NOW(),

            PRIMARY KEY (
                guild_id,
                user_id
            )
        )
        """
    )

    print(
        "[SHOP][DB] Tabla accounts preparada",
        flush=True
    )

    # ========================================================
    # TRANSACTIONS
    # ========================================================

    await db_execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (

            id BIGSERIAL PRIMARY KEY,

            guild_id BIGINT NOT NULL,

            from_user_id BIGINT,

            to_user_id BIGINT,

            amount NUMERIC(20, 2)
                NOT NULL
                CHECK (amount >= 0),

            type TEXT
                NOT NULL,

            description TEXT,

            timestamp TIMESTAMPTZ
                NOT NULL
                DEFAULT NOW()
        )
        """
    )

    print(
        "[SHOP][DB] Tabla transactions preparada",
        flush=True
    )

    # ========================================================
    # SHOP ITEMS
    # ========================================================

    await db_execute(
        """
        CREATE TABLE IF NOT EXISTS shop_items (

            id BIGSERIAL PRIMARY KEY,

            guild_id BIGINT NOT NULL,

            name TEXT NOT NULL,

            description TEXT,

            price NUMERIC(20, 2)
                NOT NULL
                DEFAULT 0
                CHECK (price >= 0),

            stock INTEGER
                NOT NULL
                DEFAULT -1
                CHECK (stock >= -1),

            role_id BIGINT,

            created_at TIMESTAMPTZ
                NOT NULL
                DEFAULT NOW()
        )
        """
    )

    print(
        "[SHOP][DB] Tabla shop_items preparada",
        flush=True
    )

    # ========================================================
    # INVENTORY
    # ========================================================

    await db_execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (

            guild_id BIGINT NOT NULL,

            user_id BIGINT NOT NULL,

            item_id BIGINT NOT NULL,

            quantity INTEGER
                NOT NULL
                DEFAULT 0
                CHECK (quantity >= 0),

            created_at TIMESTAMPTZ
                NOT NULL
                DEFAULT NOW(),

            updated_at TIMESTAMPTZ
                NOT NULL
                DEFAULT NOW(),

            PRIMARY KEY (
                guild_id,
                user_id,
                item_id
            ),

            CONSTRAINT fk_inventory_item

                FOREIGN KEY (item_id)

                REFERENCES shop_items(id)

                ON DELETE CASCADE
        )
        """
    )

    print(
        "[SHOP][DB] Tabla inventory preparada",
        flush=True
    )

    # ========================================================
    # ÍNDICES ACCOUNTS
    # ========================================================

    await db_execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_accounts_user

        ON accounts(
            guild_id,
            user_id
        )
        """
    )

    # ========================================================
    # ÍNDICES TRANSACTIONS
    # ========================================================

    await db_execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_transactions_guild

        ON transactions(
            guild_id
        )
        """
    )

    await db_execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_transactions_from_user

        ON transactions(
            guild_id,
            from_user_id
        )
        """
    )

    await db_execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_transactions_to_user

        ON transactions(
            guild_id,
            to_user_id
        )
        """
    )

    # ========================================================
    # ÍNDICES SHOP
    # ========================================================

    await db_execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_shop_items_guild

        ON shop_items(
            guild_id
        )
        """
    )

    await db_execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_shop_items_guild_name

        ON shop_items(
            guild_id,
            LOWER(name)
        )
        """
    )

    # ========================================================
    # NOMBRE ÚNICO POR SERVIDOR
    # ========================================================

    await db_execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_shop_items_unique_name

        ON shop_items(
            guild_id,
            LOWER(name)
        )
        """
    )

    # ========================================================
    # ÍNDICES INVENTORY
    # ========================================================

    await db_execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_inventory_user

        ON inventory(
            guild_id,
            user_id
        )
        """
    )

    print(
        "[SHOP][DB] Base de datos completa preparada",
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

    if interaction.guild is None:

        await interaction.response.send_message(
            "❌ Este comando solo funciona en un servidor.",
            ephemeral=True
        )

        return

    try:

        items = await db_execute(
            """
            SELECT
                id,
                name,
                description,
                price,
                stock,
                role_id

            FROM shop_items

            WHERE guild_id = %s

            ORDER BY price ASC, name ASC
            """,
            (
                interaction.guild.id,
            ),
            fetchall=True
        )

        print(
            f"[SHOP] Productos encontrados: {len(items)}",
            flush=True
        )

        if not items:

            await interaction.response.send_message(
                "🛒 La tienda está vacía.",
                ephemeral=True
            )

            return

        embed = discord.Embed(
            title="🛒 Tienda",
            description=(
                "Compra productos utilizando tus "
                "monedas."
            ),
            color=discord.Color.gold(),
            timestamp=now()
        )

        for (
            item_id,
            name,
            description,
            price,
            stock,
            role_id
        ) in items:

            if stock == -1:

                stock_text = "♾️ Ilimitado"

            elif stock <= 0:

                stock_text = "❌ Agotado"

            else:

                stock_text = (
                    f"📦 {stock} disponibles"
                )

            role_text = ""

            if role_id:

                role = interaction.guild.get_role(
                    role_id
                )

                if role:

                    role_text = (
                        f"\n🎭 Rol: {role.mention}"
                    )

            embed.add_field(
                name=(
                    f"📦 {name} — "
                    f"{format_money(price)}"
                ),
                value=(
                    f"{description or 'Sin descripción'}\n"
                    f"{stock_text}"
                    f"{role_text}"
                    f"\n\n"
                    f"Comprar: `/buy {name}`"
                ),
                inline=False
            )

        embed.set_footer(
            text=(
                f"Tienda de "
                f"{interaction.guild.name}"
            )
        )

        await interaction.response.send_message(
            embed=embed
        )

        print(
            "[SHOP] /shop respondido correctamente",
            flush=True
        )

    except Exception as error:

        print(
            f"[SHOP] ERROR en /shop: "
            f"{type(error).__name__}: {error}",
            flush=True
        )

        if not interaction.response.is_done():

            await interaction.response.send_message(
                "❌ Ha ocurrido un error al cargar la tienda.",
                ephemeral=True
            )


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

    item_name = None
    role_id = None

    total_price = Decimal("0")
    new_balance = Decimal("0")

    # ========================================================
    # TRANSACCIÓN COMPLETA
    # ========================================================

    async with _db_pool.connection() as conn:

        try:

            async with conn.transaction():

                async with conn.cursor() as cursor:

                    # ========================================
                    # PRODUCTO
                    # ========================================

                    await cursor.execute(
                        """
                        SELECT
                            id,
                            name,
                            description,
                            price,
                            stock,
                            role_id

                        FROM shop_items

                        WHERE guild_id = %s

                        AND LOWER(name) = LOWER(%s)

                        FOR UPDATE
                        """,
                        (
                            guild_id,
                            item
                        )
                    )

                    shop_item = (
                        await cursor.fetchone()
                    )

                    if shop_item is None:

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

                    # ========================================
                    # STOCK
                    # ========================================

                    if (
                        stock != -1
                        and stock < quantity
                    ):

                        await interaction.response.send_message(
                            f"❌ No hay suficiente stock.\n"
                            f"Disponible: **{stock}**.",
                            ephemeral=True
                        )

                        return

                    # ========================================
                    # CUENTA
                    # ========================================

                    await cursor.execute(
                        """
                        SELECT
                            balance

                        FROM accounts

                        WHERE guild_id = %s

                        AND user_id = %s

                        FOR UPDATE
                        """,
                        (
                            guild_id,
                            user_id
                        )
                    )

                    account = (
                        await cursor.fetchone()
                    )

                    # Si no existe, se crea automáticamente.
                    if account is None:

                        await cursor.execute(
                            """
                            INSERT INTO accounts (
                                guild_id,
                                user_id,
                                balance,
                                created_at,
                                updated_at
                            )

                            VALUES (
                                %s,
                                %s,
                                0,
                                %s,
                                %s
                            )

                            ON CONFLICT (
                                guild_id,
                                user_id
                            )

                            DO NOTHING
                            """,
                            (
                                guild_id,
                                user_id,
                                now(),
                                now()
                            )
                        )

                        await cursor.execute(
                            """
                            SELECT
                                balance

                            FROM accounts

                            WHERE guild_id = %s

                            AND user_id = %s

                            FOR UPDATE
                            """,
                            (
                                guild_id,
                                user_id
                            )
                        )

                        account = (
                            await cursor.fetchone()
                        )

                    balance = Decimal(
                        str(account[0])
                    )

                    # ========================================
                    # PRECIO
                    # ========================================

                    total_price = (
                        Decimal(str(price))
                        * quantity
                    )

                    # ========================================
                    # DINERO SUFICIENTE
                    # ========================================

                    if balance < total_price:

                        await interaction.response.send_message(
                            "❌ No tienes suficiente dinero.\n\n"
                            f"💰 Precio: **{format_money(total_price)}**\n"
                            f"💳 Tu saldo: **{format_money(balance)}**",
                            ephemeral=True
                        )

                        return

                    current = now()

                    # ========================================
                    # RESTAR DINERO
                    # ========================================

                    await cursor.execute(
                        """
                        UPDATE accounts

                        SET
                            balance =
                                balance - %s,

                            updated_at = %s

                        WHERE guild_id = %s

                        AND user_id = %s
                        """,
                        (
                            total_price,
                            current,
                            guild_id,
                            user_id
                        )
                    )

                    # ========================================
                    # TRANSACCIÓN ECONÓMICA
                    # ========================================

                    await cursor.execute(
                        """
                        INSERT INTO transactions (

                            guild_id,
                            from_user_id,
                            to_user_id,
                            amount,
                            type,
                            description,
                            timestamp
                        )

                        VALUES (

                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s
                        )
                        """,
                        (
                            guild_id,
                            user_id,
                            None,
                            total_price,
                            "shop",
                            f"Compra: {quantity}x {item_name}",
                            current
                        )
                    )

                    # ========================================
                    # STOCK
                    # ========================================

                    if stock != -1:

                        await cursor.execute(
                            """
                            UPDATE shop_items

                            SET stock =
                                stock - %s

                            WHERE id = %s
                            """,
                            (
                                quantity,
                                item_id
                            )
                        )

                    # ========================================
                    # INVENTARIO
                    # ========================================

                    await cursor.execute(
                        """
                        INSERT INTO inventory (

                            guild_id,
                            user_id,
                            item_id,
                            quantity,
                            created_at,
                            updated_at
                        )

                        VALUES (

                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s
                        )

                        ON CONFLICT (
                            guild_id,
                            user_id,
                            item_id
                        )

                        DO UPDATE SET

                            quantity =
                                inventory.quantity
                                + EXCLUDED.quantity,

                            updated_at =
                                EXCLUDED.updated_at
                        """,
                        (
                            guild_id,
                            user_id,
                            item_id,
                            quantity,
                            current,
                            current
                        )
                    )

                    new_balance = (
                        balance - total_price
                    )

        except Exception as error:

            print(
                f"[SHOP] Error en compra: "
                f"{type(error).__name__}: {error}",
                flush=True
            )

            if not interaction.response.is_done():

                await interaction.response.send_message(
                    "❌ No se pudo completar la compra.",
                    ephemeral=True
                )

            return

    # ========================================================
    # ROL
    # ========================================================

    if role_id:

        role = interaction.guild.get_role(
            role_id
        )

        if role:

            try:

                await interaction.user.add_roles(
                    role,
                    reason=(
                        f"Compra en tienda: "
                        f"{item_name}"
                    )
                )

            except discord.Forbidden:

                print(
                    f"[SHOP] No se pudo dar el rol {role_id}",
                    flush=True
                )

            except discord.HTTPException as error:

                print(
                    f"[SHOP] Error dando rol: {error}",
                    flush=True
                )

    # ========================================================
    # RESPUESTA
    # ========================================================

    embed = discord.Embed(
        title="🛒 Compra realizada",
        color=discord.Color.green(),
        timestamp=now()
    )

    embed.add_field(
        name="📦 Producto",
        value=(
            f"{item_name} × {quantity}"
        ),
        inline=False
    )

    embed.add_field(
        name="💸 Precio",
        value=format_money(
            total_price
        ),
        inline=True
    )

    embed.add_field(
        name="💰 Saldo restante",
        value=format_money(
            new_balance
        ),
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

    if user is None:
        user = interaction.user

    if user.bot:

        await interaction.response.send_message(
            "❌ Los bots no tienen inventario.",
            ephemeral=True
        )

        return

    items = await db_execute(
        """
        SELECT
            s.name,
            s.description,
            i.quantity

        FROM inventory i

        INNER JOIN shop_items s
            ON s.id = i.item_id

        WHERE i.guild_id = %s

        AND i.user_id = %s

        AND i.quantity > 0

        ORDER BY s.name ASC
        """,
        (
            interaction.guild.id,
            user.id
        ),
        fetchall=True
    )

    if not items:

        await interaction.response.send_message(
            f"🎒 **{user.display_name}** no tiene objetos.",
            ephemeral=True
        )

        return

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

    if interaction.guild is None:

        await interaction.response.send_message(
            "❌ Este comando solo funciona en un servidor.",
            ephemeral=True
        )

        return

    result = await db_execute(
        """
        SELECT COUNT(*)

        FROM shop_items

        WHERE guild_id = %s
        """,
        (
            interaction.guild.id,
        ),
        fetch=True
    )

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

def is_admin(
    interaction: discord.Interaction
):

    return (
        interaction.guild is not None
        and interaction.user.guild_permissions.administrator
    )


# ============================================================
# /SHOP_ADD
# ============================================================

@app_commands.default_permissions(
    administrator=True
)
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

    name = name.strip()

    if not name:

        await interaction.response.send_message(
            "❌ El nombre no puede estar vacío.",
            ephemeral=True
        )

        return

    parsed_role_id = None

    if role_id:

        try:

            parsed_role_id = int(
                role_id
            )

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

    try:

        await db_execute(
            """
            INSERT INTO shop_items (

                guild_id,
                name,
                description,
                price,
                stock,
                role_id,
                created_at
            )

            VALUES (

                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                interaction.guild.id,
                name,
                description,
                price,
                stock,
                parsed_role_id,
                now()
            )
        )

    except Exception as error:

        error_text = str(error).lower()

        if (
            "duplicate key" in error_text
            or "unique constraint" in error_text
        ):

            await interaction.response.send_message(
                f"❌ Ya existe **{name}** en esta tienda.",
                ephemeral=True
            )

            return

        print(
            f"[SHOP] Error creando producto: "
            f"{type(error).__name__}: {error}",
            flush=True
        )

        await interaction.response.send_message(
            "❌ No se pudo crear el producto.",
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

@app_commands.default_permissions(
    administrator=True
)
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

    item = await db_execute(
        """
        SELECT
            id,
            name

        FROM shop_items

        WHERE guild_id = %s

        AND LOWER(name) = LOWER(%s)
        """,
        (
            interaction.guild.id,
            name
        ),
        fetch=True
    )

    if item is None:

        await interaction.response.send_message(
            f"❌ No existe **{name}**.",
            ephemeral=True
        )

        return

    item_id, item_name = item

    await db_execute(
        """
        DELETE FROM shop_items

        WHERE id = %s

        AND guild_id = %s
        """,
        (
            item_id,
            interaction.guild.id
        )
    )

    await interaction.response.send_message(
        f"🗑️ Producto **{item_name}** eliminado."
    )


# ============================================================
# /SHOP_EDIT
# ============================================================

@app_commands.default_permissions(
    administrator=True
)
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

                parsed_role_id = int(
                    role_id
                )

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

    updates = []
    values = []

    if price is not None:

        updates.append(
            "price = %s"
        )

        values.append(
            price
        )

    if stock is not None:

        updates.append(
            "stock = %s"
        )

        values.append(
            stock
        )

    if description is not None:

        updates.append(
            "description = %s"
        )

        values.append(
            description
        )

    if role_id is not None:

        updates.append(
            "role_id = %s"
        )

        values.append(
            parsed_role_id
        )

    if not updates:

        await interaction.response.send_message(
            "❌ No has indicado ningún cambio.",
            ephemeral=True
        )

        return

    item = await db_execute(
        """
        SELECT id

        FROM shop_items

        WHERE guild_id = %s

        AND LOWER(name) = LOWER(%s)
        """,
        (
            interaction.guild.id,
            name
        ),
        fetch=True
    )

    if item is None:

        await interaction.response.send_message(
            f"❌ No existe **{name}**.",
            ephemeral=True
        )

        return

    item_id = item[0]

    values.extend(
        [
            item_id,
            interaction.guild.id
        ]
    )

    query = f"""
        UPDATE shop_items

        SET {", ".join(updates)}

        WHERE id = %s

        AND guild_id = %s
    """

    try:

        await db_execute(
            query,
            values
        )

    except Exception as error:

        print(
            f"[SHOP] Error editando producto: "
            f"{type(error).__name__}: {error}",
            flush=True
        )

        await interaction.response.send_message(
            "❌ No se pudo actualizar el producto.",
            ephemeral=True
        )

        return

    await interaction.response.send_message(
        f"✅ Producto **{name}** actualizado."
    )


# ============================================================
# CLOSE DATABASE
# ============================================================

async def close_shop_db():

    global _db_pool

    if _db_pool is None:
        return

    print(
        "[SHOP][DB] Cerrando pool de Neon...",
        flush=True
    )

    await _db_pool.close()

    _db_pool = None

    print(
        "[SHOP][DB] Pool cerrado",
        flush=True
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

    try:

        await init_db()

        _initialized = True

        print(
            "[SHOP] Módulo listo",
            flush=True
        )

    except Exception as error:

        print(
            f"[SHOP] ERROR inicializando DB: "
            f"{type(error).__name__}: {error}",
            flush=True
        )

        raise


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
        app_commands.Command(
            name="shop",
            description=(
                "Muestra los productos de la tienda."
            ),
            callback=shop_command
        ),
        guild=GUILD
    )

    # ========================================================
    # /BUY
    # ========================================================

    client.tree.add_command(
        app_commands.Command(
            name="buy",
            description=(
                "Compra un producto de la tienda."
            ),
            callback=buy_command
        ),
        guild=GUILD
    )

    # ========================================================
    # /INVENTORY
    # ========================================================

    client.tree.add_command(
        app_commands.Command(
            name="inventory",
            description=(
                "Muestra tu inventario."
            ),
            callback=inventory_command
        ),
        guild=GUILD
    )

    # ========================================================
    # /SHOPINFO
    # ========================================================

    client.tree.add_command(
        app_commands.Command(
            name="shopinfo",
            description=(
                "Muestra información de la tienda."
            ),
            callback=shop_info_command
        ),
        guild=GUILD
    )

    # ========================================================
    # /SHOP_ADD
    # ========================================================

    client.tree.add_command(
        app_commands.Command(
            name="shop_add",
            description=(
                "Crea un producto en la tienda."
            ),
            callback=shop_add_command
        ),
        guild=GUILD
    )

    # ========================================================
    # /SHOP_REMOVE
    # ========================================================

    client.tree.add_command(
        app_commands.Command(
            name="shop_remove",
            description=(
                "Elimina un producto de la tienda."
            ),
            callback=shop_remove_command
        ),
        guild=GUILD
    )

    # ========================================================
    # /SHOP_EDIT
    # ========================================================

    client.tree.add_command(
        app_commands.Command(
            name="shop_edit",
            description=(
                "Edita un producto de la tienda."
            ),
            callback=shop_edit_command
        ),
        guild=GUILD
    )

    # ========================================================
    # READY
    # ========================================================

    client.add_listener(
        shop_on_ready,
        "on_ready"
    )

    print(
        "[SHOP] Módulo registrado correctamente",
        flush=True
    )