import os
import asyncio
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN

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

STARTING_BALANCE = Decimal(
    os.getenv(
        "STARTING_BALANCE",
        "0"
    )
)


# ============================================================
# ACTIVIDAD DE VOZ
# ============================================================

try:

    VOICE_REWARD_PER_MINUTE = Decimal(
        os.getenv(
            "VOICE_REWARD_PER_MINUTE",
            "0.02"
        )
    )

except InvalidOperation:

    VOICE_REWARD_PER_MINUTE = Decimal(
        "0.02"
    )


VOICE_ACTIVITY_INTERVAL = int(
    os.getenv(
        "VOICE_ACTIVITY_INTERVAL",
        "60"
    )
)

VOICE_REQUIRE_OTHERS = (
    os.getenv(
        "VOICE_REQUIRE_OTHERS",
        "false"
    ).lower()
    in (
        "1",
        "true",
        "yes",
        "on"
    )
)

VOICE_IGNORE_AFK = (
    os.getenv(
        "VOICE_IGNORE_AFK",
        "true"
    ).lower()
    in (
        "1",
        "true",
        "yes",
        "on"
    )
)


# ============================================================
# GLOBAL
# ============================================================

_client = None

_initialized = False

_voice_task = None


# ============================================================
# UTILIDADES
# ============================================================

def now():

    return datetime.now(
        timezone.utc
    )


def iso(dt=None):

    if dt is None:
        dt = now()

    return dt.isoformat()


def parse_time(value):

    if not value:
        return None

    try:

        return datetime.fromisoformat(
            value
        )

    except Exception:

        return None


def decimal_value(value):

    try:

        return Decimal(
            str(value)
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError
    ):

        return Decimal(
            "0"
        )


def money_decimal(value):

    return decimal_value(
        value
    ).quantize(
        Decimal("0.01")
    )

def format_money(amount):

    amount = float(amount)

    return (
        f"{CURRENCY_SYMBOL} "
        f"{amount:,.2f}"
    )


def format_duration(seconds):

    seconds = max(
        0,
        int(seconds)
    )

    days, seconds = divmod(
        seconds,
        86400
    )

    hours, seconds = divmod(
        seconds,
        3600
    )

    minutes, seconds = divmod(
        seconds,
        60
    )

    parts = []

    if days:

        parts.append(
            f"{days}d"
        )

    if hours:

        parts.append(
            f"{hours}h"
        )

    if minutes:

        parts.append(
            f"{minutes}m"
        )

    if seconds or not parts:

        parts.append(
            f"{seconds}s"
        )

    return " ".join(
        parts
    )


# ============================================================
# DATABASE
# ============================================================

async def db_execute(
    query,
    params=(),
    fetch=False,
    fetchall=False
):

    async with aiosqlite.connect(
        DB
    ) as db:

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

    async with aiosqlite.connect(
        DB
    ) as db:

        # ====================================================
        # CUENTAS
        # ====================================================

        await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,

                balance REAL NOT NULL DEFAULT 0,

                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,

                PRIMARY KEY (
                    guild_id,
                    user_id
                )
            )
        """)

        # ====================================================
        # TRANSACCIONES
        # ====================================================

        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                guild_id INTEGER NOT NULL,

                from_user_id INTEGER,
                to_user_id INTEGER,

                amount REAL NOT NULL,

                type TEXT NOT NULL,

                description TEXT,

                timestamp TEXT NOT NULL
            )
        """)

        # ====================================================
        # ACTIVIDAD DE VOZ
        # ====================================================

        await db.execute("""
            CREATE TABLE IF NOT EXISTS voice_activity (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,

                total_seconds INTEGER NOT NULL DEFAULT 0,

                total_earned REAL NOT NULL DEFAULT 0,

                updated_at TEXT NOT NULL,

                PRIMARY KEY (
                    guild_id,
                    user_id
                )
            )
        """)

        # ====================================================
        # SESIONES DE VOZ
        # ====================================================

        await db.execute("""
            CREATE TABLE IF NOT EXISTS voice_sessions (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,

                joined_at TEXT NOT NULL,
                last_paid_at TEXT NOT NULL,

                PRIMARY KEY (
                    guild_id,
                    user_id
                )
            )
        """)

        # ====================================================
        # INDICES
        # ====================================================

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

            ON transactions(
                guild_id
            )
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

        await db.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_voice_activity_guild

            ON voice_activity(
                guild_id,
                total_seconds DESC
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

async def ensure_account(
    guild_id,
    user_id
):

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

        return decimal_value(
            existing[0]
        )

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
            float(
                STARTING_BALANCE
            ),
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
                float(
                    STARTING_BALANCE
                ),
                "initial",
                "Saldo inicial",
                current
            )
        )

    return STARTING_BALANCE


async def get_balance(
    guild_id,
    user_id
):

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

        return Decimal(
            "0"
        )

    return decimal_value(
        result[0]
    )


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

    amount = float(amount)

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
            float(amount),
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
            float(amount),
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
            float(amount),
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
            float(amount),
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

    amount = float(amount)

    if amount <= 0:

        return (
            False,
            "La cantidad debe ser mayor que 0."
        )

    if from_user_id == to_user_id:

        return (
            False,
            "No puedes enviarte monedas a ti mismo."
        )

    sender_balance = await get_balance(
        guild_id,
        from_user_id
    )

    if sender_balance < amount:

        return (
            False,
            "No tienes suficientes monedas."
        )

    await ensure_account(
        guild_id,
        to_user_id
    )

    current = iso()

    async with aiosqlite.connect(
        DB
    ) as db:

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
                float(amount),
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
                float(amount),
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
                float(amount),
                "transfer",
                "Transferencia entre usuarios",
                current
            )
        )

        await db.commit()

    return (
        True,
        None
    )


# ============================================================
# VOICE ACTIVITY
# ============================================================

async def ensure_voice_activity(
    guild_id,
    user_id
):

    existing = await db_execute(
        """
        SELECT total_seconds
        FROM voice_activity

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

        return

    await db_execute(
        """
        INSERT INTO voice_activity (
            guild_id,
            user_id,
            total_seconds,
            total_earned,
            updated_at
        )

        VALUES (?, ?, 0, 0, ?)
        """,
        (
            guild_id,
            user_id,
            iso()
        )
    )


async def start_voice_session(
    guild_id,
    user_id
):

    await ensure_account(
        guild_id,
        user_id
    )

    await ensure_voice_activity(
        guild_id,
        user_id
    )

    current = iso()

    existing = await db_execute(
        """
        SELECT user_id

        FROM voice_sessions

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

        return

    await db_execute(
        """
        INSERT INTO voice_sessions (
            guild_id,
            user_id,
            joined_at,
            last_paid_at
        )

        VALUES (?, ?, ?, ?)
        """,
        (
            guild_id,
            user_id,
            current,
            current
        )
    )

    print(
        f"[ECONOMY][VOICE] "
        f"Usuario {user_id} comenzó actividad",
        flush=True
    )


async def stop_voice_session(
    guild_id,
    user_id
):

    session = await db_execute(
        """
        SELECT
            joined_at,
            last_paid_at

        FROM voice_sessions

        WHERE guild_id = ?
        AND user_id = ?
        """,
        (
            guild_id,
            user_id
        ),
        fetch=True
    )

    if not session:

        return

    # ========================================================
    # IMPORTANTE:
    # Calculamos desde last_paid_at, NO desde joined_at.
    #
    # Esto evita pagar dos veces el tiempo que ya procesó
    # el loop.
    # ========================================================

    last_paid_at = parse_time(
        session[1]
    )

    if last_paid_at:

        elapsed = int(
            (
                now() - last_paid_at
            ).total_seconds()
        )

        complete_minutes = (
            elapsed // 60
        )

        if complete_minutes > 0:

            seconds_to_process = (
                complete_minutes * 60
            )

            await add_voice_time(
                guild_id,
                user_id,
                seconds_to_process
            )

    await db_execute(
        """
        DELETE FROM voice_sessions

        WHERE guild_id = ?
        AND user_id = ?
        """,
        (
            guild_id,
            user_id
        )
    )

    print(
        f"[ECONOMY][VOICE] "
        f"Usuario {user_id} salió de voz",
        flush=True
    )


async def add_voice_time(
    guild_id,
    user_id,
    seconds
):

    seconds = int(seconds)

    if seconds < 60:
        return Decimal("0")

    # Solo minutos completos
    minutes = seconds // 60

    seconds_to_process = minutes * 60

    reward = (
        VOICE_REWARD_PER_MINUTE *
        Decimal(minutes)
    )

    reward = reward.quantize(
        Decimal("0.01"),
        rounding=ROUND_DOWN
    )

    current = iso()

    await ensure_voice_activity(
        guild_id,
        user_id
    )

    await ensure_account(
        guild_id,
        user_id
    )

    async with aiosqlite.connect(DB) as db:

        # ================================================
        # GUARDAR TIEMPO DE VOZ
        # ================================================

        await db.execute(
            """
            UPDATE voice_activity

            SET
                total_seconds =
                    total_seconds + ?,

                total_earned =
                    total_earned + ?,

                updated_at = ?

            WHERE guild_id = ?
            AND user_id = ?
            """,
            (
                seconds_to_process,
                float(reward),
                current,
                guild_id,
                user_id
            )
        )

        # ================================================
        # AÑADIR DINERO AL SALDO
        # ================================================

        await db.execute(
            """
            UPDATE accounts

            SET
                balance =
                    balance + ?,

                updated_at = ?

            WHERE guild_id = ?
            AND user_id = ?
            """,
            (
                float(reward),
                current,
                guild_id,
                user_id
            )
        )

        # ================================================
        # REGISTRAR TRANSACCIÓN
        # ================================================

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
                None,
                user_id,
                float(reward),
                "voice_activity",
                f"Actividad en voz: {minutes} minuto(s)",
                current
            )
        )

        await db.commit()

    return reward
# ============================================================
# COMPROBAR ACTIVIDAD
# ============================================================

def user_counts_for_voice(
    member: discord.Member
):

    if member.bot:

        return False

    voice_state = member.voice

    if voice_state is None:

        return False

    channel = voice_state.channel

    if channel is None:

        return False

    # ========================================================
    # AFK
    # ========================================================

    if (
        VOICE_IGNORE_AFK
        and member.guild.afk_channel
        and channel.id ==
            member.guild.afk_channel.id
    ):

        return False

    # ========================================================
    # DEAFEN
    # ========================================================

    if (
        voice_state.deaf
        or voice_state.self_deaf
    ):

        return False

    # ========================================================
    # OTRAS PERSONAS
    # ========================================================

    if VOICE_REQUIRE_OTHERS:

        humans = [
            m
            for m in channel.members
            if not m.bot
        ]

        if len(humans) < 2:

            return False

    return True


# ============================================================
# PROCESAR SESIONES
# ============================================================

async def process_voice_sessions():

    if _client is None:

        return

    guild = _client.get_guild(
        GUILD_ID
    )

    if guild is None:

        return

    rows = await db_execute(
        """
        SELECT
            user_id,
            last_paid_at

        FROM voice_sessions

        WHERE guild_id = ?
        """,
        (
            GUILD_ID,
        ),
        fetchall=True
    )

    if not rows:

        return

    for (
        user_id,
        last_paid_at_value
    ) in rows:

        member = guild.get_member(
            user_id
        )

        # ====================================================
        # YA NO CUENTA
        # ====================================================

        if (
            member is None
            or not user_counts_for_voice(
                member
            )
        ):

            await stop_voice_session(
                GUILD_ID,
                user_id
            )

            continue

        # ====================================================
        # SIGUE ACTIVO
        # ====================================================

        last_paid_at = parse_time(
            last_paid_at_value
        )

        if last_paid_at is None:

            last_paid_at = now()

        current = now()

        elapsed = int(
            (
                current - last_paid_at
            ).total_seconds()
        )

        if elapsed < 60:

            continue

        complete_minutes = (
            elapsed // 60
        )

        seconds_to_process = (
            complete_minutes * 60
        )

        reward = await add_voice_time(
            GUILD_ID,
            user_id,
            seconds_to_process
        )

        # ====================================================
        # AVANZAR last_paid_at SOLO EL TIEMPO PAGADO
        # ====================================================

        new_last_paid = (
            last_paid_at.timestamp()
            + seconds_to_process
        )

        new_last_paid_dt = (
            datetime.fromtimestamp(
                new_last_paid,
                tz=timezone.utc
            )
        )

        await db_execute(
            """
            UPDATE voice_sessions

            SET last_paid_at = ?

            WHERE guild_id = ?
            AND user_id = ?
            """,
            (
                iso(
                    new_last_paid_dt
                ),
                GUILD_ID,
                user_id
            )
        )

        if reward > 0:

            print(
                f"[ECONOMY][VOICE] "
                f"{user_id}: "
                f"+{format_money(reward)} "
                f"({complete_minutes} min)",
                flush=True
            )


# ============================================================
# LOOP DE VOZ
# ============================================================

async def voice_activity_loop():

    print(
        "[ECONOMY][VOICE] "
        "Sistema de actividad iniciado",
        flush=True
    )

    await asyncio.sleep(
        10
    )

    while True:

        try:

            await process_voice_sessions()

        except asyncio.CancelledError:

            print(
                "[ECONOMY][VOICE] "
                "Sistema detenido",
                flush=True
            )

            raise

        except Exception as error:

            print(
                "[ECONOMY][VOICE] "
                f"Error: {error}",
                flush=True
            )

        await asyncio.sleep(
            max(
                10,
                VOICE_ACTIVITY_INTERVAL
            )
        )


# ============================================================
# VOICE STATE UPDATE
# ============================================================

async def economy_on_voice_state_update(
    member,
    before,
    after
):

    if member.guild.id != GUILD_ID:

        return

    if member.bot:

        return

    was_in_voice = (
        before.channel is not None
    )

    is_in_voice = (
        after.channel is not None
    )

    # ========================================================
    # SALE DE VOZ
    # ========================================================

    if was_in_voice and not is_in_voice:

        await stop_voice_session(
            member.guild.id,
            member.id
        )

        return

    # ========================================================
    # CAMBIO DE CANAL
    # ========================================================

    if (
        was_in_voice
        and is_in_voice
        and before.channel.id != after.channel.id
    ):

        await stop_voice_session(
            member.guild.id,
            member.id
        )

        if user_counts_for_voice(
            member
        ):

            await start_voice_session(
                member.guild.id,
                member.id
            )

        return

    # ========================================================
    # ENTRA EN VOZ
    # ========================================================

    if not was_in_voice and is_in_voice:

        if user_counts_for_voice(
            member
        ):

            await start_voice_session(
                member.guild.id,
                member.id
            )

        return

    # ========================================================
    # MUTE / DEAF / CAMBIO DE CONDICIÓN
    # ========================================================

    if is_in_voice:

        valid_before = (
            before.channel is not None
            and user_counts_for_voice(
                member
            )
        )

        valid_after = (
            user_counts_for_voice(
                member
            )
        )

        if (
            not valid_before
            and valid_after
        ):

            await start_voice_session(
                member.guild.id,
                member.id
            )

        elif (
            valid_before
            and not valid_after
        ):

            await stop_voice_session(
                member.guild.id,
                member.id
            )


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

    voice_stats = await db_execute(
        """
        SELECT
            total_seconds,
            total_earned

        FROM voice_activity

        WHERE guild_id = ?
        AND user_id = ?
        """,
        (
            interaction.guild.id,
            member.id
        ),
        fetch=True
    )

    if voice_stats:

        total_seconds = voice_stats[0]
        total_earned = decimal_value(
            voice_stats[1]
        )

    else:

        total_seconds = 0
        total_earned = Decimal(
            "0"
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
        name=f"{CURRENCY_SYMBOL} Saldo",
        value=format_money(
            balance
        ),
        inline=False
    )

    embed.add_field(
        name="🎙️ Tiempo en voz",
        value=format_duration(
            total_seconds
        ),
        inline=True
    )

    embed.add_field(
        name="💸 Ganado en voz",
        value=format_money(
            total_earned
        ),
        inline=True
    )

    embed.set_footer(
        text=(
            f"Economía de "
            f"{interaction.guild.name}"
        )
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
        value=format_money(
            sender_balance
        ),
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

    for position, (
        user_id,
        balance
    ) in enumerate(
        rows,
        start=1
    ):

        member = (
            interaction.guild.get_member(
                user_id
            )
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
        description="\n".join(
            ranking
        ),
        color=discord.Color.gold(),
        timestamp=now()
    )

    embed.set_footer(
        text=(
            f"Top 10 — "
            f"{interaction.guild.name}"
        )
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
        description=(
            "Sistema económico basado "
            "en actividad en canales de voz."
        ),
        color=discord.Color.gold()
    )

    embed.add_field(
        name="Moneda",
        value=(
            f"{CURRENCY_SYMBOL} "
            f"{CURRENCY}"
        ),
        inline=True
    )

    embed.add_field(
        name="🎙️ Recompensa",
        value=(
            f"{format_money(VOICE_REWARD_PER_MINUTE)} / minuto"
        ),
        inline=True
    )

    embed.add_field(
        name="⏱️ Comprobación",
        value=(
            f"Cada "
            f"{VOICE_ACTIVITY_INTERVAL}s"
        ),
        inline=True
    )

    embed.add_field(
        name="👥 Requiere otra persona",
        value=(
            "Sí"
            if VOICE_REQUIRE_OTHERS
            else "No"
        ),
        inline=True
    )

    embed.add_field(
        name="💤 Canal AFK",
        value=(
            "Ignorado"
            if VOICE_IGNORE_AFK
            else "Cuenta"
        ),
        inline=True
    )

    embed.add_field(
        name=f"{CURRENCY_SYMBOL} Saldo inicial",
        value=format_money(
            STARTING_BALANCE
        ),
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
    global _voice_task

    if _initialized:

        return

    print(
        "[ECONOMY] Inicializando módulo...",
        flush=True
    )

    await init_db()

    _initialized = True

    # ========================================================
    # SINCRONIZAR USUARIOS QUE YA ESTÁN EN VOZ
    # ========================================================

    guild = _client.get_guild(
        GUILD_ID
    )

    if guild is not None:

        for channel in guild.voice_channels:

            for member in channel.members:

                if member.bot:

                    continue

                if user_counts_for_voice(
                    member
                ):

                    existing = await db_execute(
                        """
                        SELECT user_id

                        FROM voice_sessions

                        WHERE guild_id = ?
                        AND user_id = ?
                        """,
                        (
                            GUILD_ID,
                            member.id
                        ),
                        fetch=True
                    )

                    if existing:

                        # El bot estuvo apagado.
                        # No regalamos ese tiempo.

                        await db_execute(
                            """
                            UPDATE voice_sessions

                            SET
                                joined_at = ?,
                                last_paid_at = ?

                            WHERE guild_id = ?
                            AND user_id = ?
                            """,
                            (
                                iso(),
                                iso(),
                                GUILD_ID,
                                member.id
                            )
                        )

                    else:

                        await start_voice_session(
                            GUILD_ID,
                            member.id
                        )

    # ========================================================
    # INICIAR LOOP
    # ========================================================

    if _voice_task is None:

        _voice_task = asyncio.create_task(
            voice_activity_loop()
        )

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
    # /BALANCE
    # ========================================================

    client.tree.add_command(
        discord.app_commands.Command(
            name="balance",
            description=(
                "Muestra el saldo y actividad "
                "de un usuario"
            ),
            callback=economy_balance
        ),
        guild=GUILD
    )

    # ========================================================
    # /PAY
    # ========================================================

    client.tree.add_command(
        discord.app_commands.Command(
            name="pay",
            description=(
                "Envía monedas a otro usuario"
            ),
            callback=economy_pay
        ),
        guild=GUILD
    )

    # ========================================================
    # /LEADERBOARD
    # ========================================================

    client.tree.add_command(
        discord.app_commands.Command(
            name="leaderboard",
            description=(
                "Muestra el ranking económico"
            ),
            callback=economy_leaderboard
        ),
        guild=GUILD
    )

    # ========================================================
    # /ECONOMYINFO
    # ========================================================

    client.tree.add_command(
        discord.app_commands.Command(
            name="economyinfo",
            description=(
                "Muestra la configuración "
                "de la economía"
            ),
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

    # ========================================================
    # VOICE STATE UPDATE
    # ========================================================

    client.add_listener(
        economy_on_voice_state_update,
        "on_voice_state_update"
    )

    print(
        "[ECONOMY] Módulo registrado correctamente",
        flush=True
    )