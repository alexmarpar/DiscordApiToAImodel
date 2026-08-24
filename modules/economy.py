import os
import random
from datetime import datetime, timezone

import aiosqlite
import discord


# ============================================================
# CONFIG
# ============================================================

DB = os.getenv("ECONOMY_DB", "economy.db")

GUILD_ID = int(os.getenv("GUILD_ID", "0"))

if GUILD_ID == 0:
    raise RuntimeError("GUILD_ID no está definido")

GUILD = discord.Object(id=GUILD_ID)


# ============================================================
# MONEDA
# ============================================================

CURRENCY = os.getenv(
    "CURRENCY_NAME",
    "Coins"
)

CURRENCY_SYMBOL = os.getenv(
    "CURRENCY_SYMBOL",
    "💰"
)


# ============================================================
# SALDO INICIAL
# ============================================================

STARTING_BALANCE = int(
    os.getenv("STARTING_BALANCE", "0")
)


# ============================================================
# RECOMPENSAS
# ============================================================

DAILY_REWARD = int(
    os.getenv("DAILY_REWARD", "10")
)

WORK_MIN = int(
    os.getenv("WORK_MIN", "1")
)

WORK_MAX = int(
    os.getenv("WORK_MAX", "10")
)


# ============================================================
# COOLDOWNS
# ============================================================

DAILY_COOLDOWN = 86400
WORK_COOLDOWN = 86400


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


def iso(dt=None):

    if dt is None:
        dt = now()

    return dt.isoformat()


def parse_time(value):

    if not value:
        return None

    try:
        return datetime.fromisoformat(value)

    except Exception:
        return None


def format_money(amount):

    return f"{CURRENCY_SYMBOL} {amount:,}"


def format_duration(seconds):

    seconds = max(0, int(seconds))

    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    parts = []

    if days:
        parts.append(f"{days}d")

    if hours:
        parts.append(f"{hours}h")

    if minutes:
        parts.append(f"{minutes}m")

    if seconds or not parts:
        parts.append(f"{seconds}s")

    return " ".join(parts)


# ============================================================
# DATABASE
# ============================================================

async def db_execute(
    query,
    params=(),
    fetch=False,
    fetchall=False
):

    async with aiosqlite.connect(DB) as db:

        cursor = await db.execute(
            query,
            params
        )

        result = None

        if fetch:
            result = await cursor.fetchone()

        elif fetchall:
            result = await cursor.fetchall()

        await db.commit()

        return result


# ============================================================
# INIT DATABASE
# ============================================================

async def init_db():

    print(
        "[ECONOMY][DB] Inicializando...",
        flush=True
    )

    async with aiosqlite.connect(DB) as db:

        await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,

                balance INTEGER NOT NULL DEFAULT 0,

                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,

                last_daily TEXT,
                last_work TEXT,

                PRIMARY KEY (
                    guild_id,
                    user_id
                )
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                guild_id INTEGER NOT NULL,

                from_user_id INTEGER,
                to_user_id INTEGER,

                amount INTEGER NOT NULL,

                type TEXT NOT NULL,

                description TEXT,

                timestamp TEXT NOT NULL
            )
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_accounts_guild_balance

            ON accounts(
                guild_id,
                balance DESC
            )
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_transactions_guild

            ON transactions(guild_id)
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_transactions_users

            ON transactions(
                guild_id,
                from_user_id,
                to_user_id
            )
        """)

        await db.commit()

    print(
        "[ECONOMY][DB] Base de datos lista",
        flush=True
    )


# ============================================================
# CUENTAS
# ============================================================

async def ensure_account(guild_id, user_id):

    current = iso()

    existing = await db_execute(
        """
        SELECT balance
        FROM accounts
        WHERE guild_id = ?
        AND user_id = ?
        """,
        (
            guild_id,
            user_id
        ),
        fetch=True
    )

    if existing:
        return existing[0]

    await db_execute(
        """
        INSERT INTO accounts (
            guild_id,
            user_id,
            balance,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            guild_id,
            user_id,
            STARTING_BALANCE,
            current,
            current
        )
    )

    if STARTING_BALANCE > 0:

        await db_execute(
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
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                None,
                user_id,
                STARTING_BALANCE,
                "initial",
                "Saldo inicial",
                current
            )
        )

    return STARTING_BALANCE


async def get_balance(guild_id, user_id):

    await ensure_account(
        guild_id,
        user_id
    )

    result = await db_execute(
        """
        SELECT balance
        FROM accounts
        WHERE guild_id = ?
        AND user_id = ?
        """,
        (
            guild_id,
            user_id
        ),
        fetch=True
    )

    if not result:
        return 0

    return result[0]


# ============================================================
# ADD MONEY
# ============================================================

async def add_money(
    guild_id,
    user_id,
    amount,
    transaction_type="reward",
    description=None
):

    amount = int(amount)

    if amount <= 0:
        return False

    await ensure_account(
        guild_id,
        user_id
    )

    current = iso()

    await db_execute(
        """
        UPDATE accounts
        SET
            balance = balance + ?,
            updated_at = ?
        WHERE guild_id = ?
        AND user_id = ?
        """,
        (
            amount,
            current,
            guild_id,
            user_id
        )
    )

    await db_execute(
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
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            guild_id,
            None,
            user_id,
            amount,
            transaction_type,
            description,
            current
        )
    )

    return True


# ============================================================
# REMOVE MONEY
# ============================================================

async def remove_money(
    guild_id,
    user_id,
    amount,
    transaction_type="remove",
    description=None
):

    amount = int(amount)

    if amount <= 0:
        return False

    balance = await get_balance(
        guild_id,
        user_id
    )

    if balance < amount:
        return False

    current = iso()

    await db_execute(
        """
        UPDATE accounts
        SET
            balance = balance - ?,
            updated_at = ?
        WHERE guild_id = ?
        AND user_id = ?
        """,
        (
            amount,
            current,
            guild_id,
            user_id
        )
    )

    await db_execute(
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
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            guild_id,
            user_id,
            None,
            amount,
            transaction_type,
            description,
            current
        )
    )

    return True


# ============================================================
# TRANSFER
# ============================================================

async def transfer_money(
    guild_id,
    from_user_id,
    to_user_id,
    amount
):

    amount = int(amount)

    if amount <= 0:
        return False, "La cantidad debe ser mayor que 0."

    if from_user_id == to_user_id:
        return False, "No puedes enviarte monedas a ti mismo."

    sender_balance = await get_balance(
        guild_id,
        from_user_id
    )

    if sender_balance < amount:
        return False, "No tienes suficientes monedas."

    await ensure_account(
        guild_id,
        to_user_id
    )

    current = iso()

    async with aiosqlite.connect(DB) as db:

        await db.execute(
            """
            UPDATE accounts
            SET
                balance = balance - ?,
                updated_at = ?
            WHERE guild_id = ?
            AND user_id = ?
            """,
            (
                amount,
                current,
                guild_id,
                from_user_id
            )
        )

        await db.execute(
            """
            UPDATE accounts
            SET
                balance = balance + ?,
                updated_at = ?
            WHERE guild_id = ?
            AND user_id = ?
            """,
            (
                amount,
                current,
                guild_id,
                to_user_id
            )
        )

        await db.execute(
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
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                from_user_id,
                to_user_id,
                amount,
                "transfer",
                "Transferencia entre usuarios",
                current
            )
        )

        await db.commit()

    return True, None


# ============================================================
# COOLDOWNS
# ============================================================

async def get_cooldown(
    guild_id,
    user_id,
    column
):

    if column not in (
        "last_daily",
        "last_work"
    ):
        return None

    result = await db_execute(
        f"""
        SELECT {column}
        FROM accounts
        WHERE guild_id = ?
        AND user_id = ?
        """,
        (
            guild_id,
            user_id
        ),
        fetch=True
    )

    if not result:
        return None

    return parse_time(result[0])


async def set_cooldown(
    guild_id,
    user_id,
    column
):

    if column not in (
        "last_daily",
        "last_work"
    ):
        return

    current = iso()

    await db_execute(
        f"""
        UPDATE accounts
        SET
            {column} = ?,
            updated_at = ?
        WHERE guild_id = ?
        AND user_id = ?
        """,
        (
            current,
            current,
            guild_id,
            user_id
        )
    )


def remaining_cooldown(
    last_use,
    cooldown
):

    if not last_use:
        return 0

    elapsed = (
        now() - last_use
    ).total_seconds()

    remaining = cooldown - elapsed

    return max(0, int(remaining))


# ============================================================
# /BALANCE
# ============================================================

async def economy_balance(
    interaction: discord.Interaction,
    member: discord.Member = None
):

    if interaction.guild is None:

        await interaction.response.send_message(
            "❌ Este comando solo funciona en un servidor.",
            ephemeral=True
        )

        return

    if member is None:
        member = interaction.user

    if member.bot:

        await interaction.response.send_message(
            "❌ Los bots no tienen cuentas.",
            ephemeral=True
        )

        return

    balance = await get_balance(
        interaction.guild.id,
        member.id
    )

    embed = discord.Embed(
        title="💰 Saldo",
        color=discord.Color.gold(),
        timestamp=now()
    )

    embed.set_author(
        name=member.display_name,
        icon_url=member.display_avatar.url
    )

    embed.add_field(
        name=f"{CURRENCY_SYMBOL}Cripsys",
        value=format_money(balance),
        inline=False
    )

    embed.set_footer(
        text=f"Economía de {interaction.guild.name}"
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# /DAILY
# ============================================================

async def economy_daily(
    interaction: discord.Interaction
):

    if interaction.guild is None:

        await interaction.response.send_message(
            "❌ Este comando solo funciona en un servidor.",
            ephemeral=True
        )

        return

    user = interaction.user

    if user.bot:

        await interaction.response.send_message(
            "❌ Los bots no pueden utilizar la economía.",
            ephemeral=True
        )

        return

    guild_id = interaction.guild.id

    await ensure_account(
        guild_id,
        user.id
    )

    last_daily = await get_cooldown(
        guild_id,
        user.id,
        "last_daily"
    )

    remaining = remaining_cooldown(
        last_daily,
        DAILY_COOLDOWN
    )

    if remaining > 0:

        await interaction.response.send_message(
            "⏳ Ya has recogido tu recompensa diaria.\n"
            f"Podrás volver a recogerla en "
            f"**{format_duration(remaining)}**.",
            ephemeral=True
        )

        return

    await add_money(
        guild_id,
        user.id,
        DAILY_REWARD,
        transaction_type="daily",
        description="Recompensa diaria"
    )

    await set_cooldown(
        guild_id,
        user.id,
        "last_daily"
    )

    balance = await get_balance(
        guild_id,
        user.id
    )

    embed = discord.Embed(
        title="🎁 Recompensa diaria",
        description=(
            f"Has recibido "
            f"**{format_money(DAILY_REWARD)}**."
        ),
        color=discord.Color.green(),
        timestamp=now()
    )

    embed.add_field(
        name="💰 Nuevo saldo",
        value=format_money(balance),
        inline=False
    )

    embed.set_footer(
        text="Vuelve mañana para otra recompensa"
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# /WORK
# ============================================================

async def economy_work(
    interaction: discord.Interaction
):

    if interaction.guild is None:

        await interaction.response.send_message(
            "❌ Este comando solo funciona en un servidor.",
            ephemeral=True
        )

        return

    user = interaction.user

    if user.bot:

        await interaction.response.send_message(
            "❌ Los bots no pueden trabajar.",
            ephemeral=True
        )

        return

    guild_id = interaction.guild.id

    await ensure_account(
        guild_id,
        user.id
    )

    last_work = await get_cooldown(
        guild_id,
        user.id,
        "last_work"
    )

    remaining = remaining_cooldown(
        last_work,
        WORK_COOLDOWN
    )

    if remaining > 0:

        await interaction.response.send_message(
            "⏳ Todavía estás trabajando.\n"
            f"Podrás volver a trabajar en "
            f"**{format_duration(remaining)}**.",
            ephemeral=True
        )

        return

    reward = random.randint(
        WORK_MIN,
        WORK_MAX
    )

    jobs = [
        "💻 Has programado una aplicación.",
        "🍕 Has trabajado en una pizzería.",
        "🚗 Has lavado algunos coches.",
        "📦 Has repartido paquetes.",
        "🎮 Has probado videojuegos.",
        "🔧 Has arreglado un ordenador.",
        "🐶 Has paseado unos perros.",
        "🏗️ Has ayudado en una obra."
    ]

    job = random.choice(jobs)

    await add_money(
        guild_id,
        user.id,
        reward,
        transaction_type="work",
        description="Recompensa por trabajar"
    )

    await set_cooldown(
        guild_id,
        user.id,
        "last_work"
    )

    balance = await get_balance(
        guild_id,
        user.id
    )

    embed = discord.Embed(
        title="💼 Trabajo completado",
        description=(
            f"{job}\n\n"
            f"Has ganado **{format_money(reward)}**."
        ),
        color=discord.Color.blue(),
        timestamp=now()
    )

    embed.add_field(
        name="💰 Saldo",
        value=format_money(balance),
        inline=False
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# /PAY
# ============================================================

async def economy_pay(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: int
):

    if interaction.guild is None:

        await interaction.response.send_message(
            "❌ Este comando solo funciona en un servidor.",
            ephemeral=True
        )

        return

    sender = interaction.user

    if sender.bot:

        await interaction.response.send_message(
            "❌ Los bots no pueden utilizar la economía.",
            ephemeral=True
        )

        return

    if member.bot:

        await interaction.response.send_message(
            "❌ No puedes enviar monedas a un bot.",
            ephemeral=True
        )

        return

    if amount <= 0:

        await interaction.response.send_message(
            "❌ La cantidad debe ser mayor que 0.",
            ephemeral=True
        )

        return

    success, error = await transfer_money(
        interaction.guild.id,
        sender.id,
        member.id,
        amount
    )

    if not success:

        await interaction.response.send_message(
            f"❌ {error}",
            ephemeral=True
        )

        return

    sender_balance = await get_balance(
        interaction.guild.id,
        sender.id
    )

    embed = discord.Embed(
        title="💸 Transferencia realizada",
        description=(
            f"{sender.mention} ha enviado "
            f"**{format_money(amount)}** a "
            f"{member.mention}."
        ),
        color=discord.Color.green(),
        timestamp=now()
    )

    embed.add_field(
        name="💰 Tu saldo",
        value=format_money(sender_balance),
        inline=False
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# /LEADERBOARD
# ============================================================

async def economy_leaderboard(
    interaction: discord.Interaction
):

    if interaction.guild is None:

        await interaction.response.send_message(
            "❌ Este comando solo funciona en un servidor.",
            ephemeral=True
        )

        return

    rows = await db_execute(
        """
        SELECT
            user_id,
            balance
        FROM accounts
        WHERE guild_id = ?
        ORDER BY balance DESC
        LIMIT 10
        """,
        (
            interaction.guild.id,
        ),
        fetchall=True
    )

    if not rows:

        await interaction.response.send_message(
            "📊 Todavía no hay cuentas.",
            ephemeral=True
        )

        return

    ranking = []

    position_emojis = {
        1: "🥇",
        2: "🥈",
        3: "🥉"
    }

    for position, (user_id, balance) in enumerate(
        rows,
        start=1
    ):

        member = interaction.guild.get_member(
            user_id
        )

        if member is None:
            name = f"<@{user_id}>"
        else:
            name = member.mention

        medal = position_emojis.get(
            position,
            f"**{position}.**"
        )

        ranking.append(
            f"{medal} {name} — "
            f"**{format_money(balance)}**"
        )

    embed = discord.Embed(
        title="🏆 Ranking económico",
        description="\n".join(ranking),
        color=discord.Color.gold(),
        timestamp=now()
    )

    embed.set_footer(
        text=f"Top 10 — {interaction.guild.name}"
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# /ECONOMYINFO
# ============================================================

async def economy_info(
    interaction: discord.Interaction
):

    embed = discord.Embed(
        title=f"{CURRENCY_SYMBOL} Economía",
        description="Sistema económico del servidor.",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="Moneda",
        value=f"{CURRENCY_SYMBOL} {CURRENCY}",
        inline=True
    )

    embed.add_field(
        name="🎁 Daily",
        value=format_money(DAILY_REWARD),
        inline=True
    )

    embed.add_field(
        name="💼 Work",
        value=(
            f"{format_money(WORK_MIN)} - "
            f"{format_money(WORK_MAX)}"
        ),
        inline=True
    )

    embed.add_field(
        name="⏱️ Daily",
        value=format_duration(DAILY_COOLDOWN),
        inline=True
    )

    embed.add_field(
        name="⏱️ Work",
        value=format_duration(WORK_COOLDOWN),
        inline=True
    )

    embed.add_field(
        name=f"{CURRENCY_SYMBOL} Saldo inicial",
        value=format_money(STARTING_BALANCE),
        inline=True
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# READY
# ============================================================

async def economy_on_ready():

    global _initialized

    if _initialized:
        return

    print(
        "[ECONOMY] Inicializando módulo...",
        flush=True
    )

    await init_db()

    _initialized = True

    print(
        "[ECONOMY] Módulo listo",
        flush=True
    )


# ============================================================
# SETUP
# ============================================================

def setup_economy(client):

    global _client

    if _client is not None:

        print(
            "[ECONOMY] Módulo ya registrado",
            flush=True
        )

        return

    _client = client

    print(
        "[ECONOMY] Registrando módulo...",
        flush=True
    )

    # ========================================================
    # TODOS LOS COMANDOS SE REGISTRAN EN EL GUILD
    # ========================================================

    client.tree.add_command(
        discord.app_commands.Command(
            name="balance",
            description="Muestra el saldo de un usuario",
            callback=economy_balance
        ),
        guild=GUILD
    )

    client.tree.add_command(
        discord.app_commands.Command(
            name="daily",
            description="Recoge tu recompensa diaria",
            callback=economy_daily
        ),
        guild=GUILD
    )

    client.tree.add_command(
        discord.app_commands.Command(
            name="work",
            description="Trabaja para ganar monedas",
            callback=economy_work
        ),
        guild=GUILD
    )

    client.tree.add_command(
        discord.app_commands.Command(
            name="pay",
            description="Envía monedas a otro usuario",
            callback=economy_pay
        ),
        guild=GUILD
    )

    client.tree.add_command(
        discord.app_commands.Command(
            name="leaderboard",
            description="Muestra el ranking económico",
            callback=economy_leaderboard
        ),
        guild=GUILD
    )

    client.tree.add_command(
        discord.app_commands.Command(
            name="economyinfo",
            description="Muestra la configuración de la economía",
            callback=economy_info
        ),
        guild=GUILD
    )

    # ========================================================
    # READY
    # ========================================================

    client.add_listener(
        economy_on_ready,
        "on_ready"
    )

    print(
        "[ECONOMY] Módulo registrado correctamente",
        flush=True
    )