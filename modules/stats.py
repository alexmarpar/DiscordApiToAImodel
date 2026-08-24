import os
from datetime import datetime, timezone, timedelta

import aiosqlite
import discord
from discord import app_commands


# ============================================================
# CONFIG
# ============================================================

GUILD_ID = int(os.getenv("GUILD_ID", "0"))
DB = "stats.db"

if GUILD_ID == 0:
    raise RuntimeError("GUILD_ID no está definido")

GUILD = discord.Object(id=GUILD_ID)


# ============================================================
# ESTADO DEL MÓDULO
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


def format_duration(seconds):
    seconds = int(max(0, seconds))

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

        if fetch:
            result = await cursor.fetchone()

        elif fetchall:
            result = await cursor.fetchall()

        else:
            result = None

        await db.commit()

        return result


# ============================================================
# DATABASE
# ============================================================

async def init_db():

    print("[STATS][DB] Inicializando...", flush=True)

    async with aiosqlite.connect(DB) as db:

        # ----------------------------------------------------
        # USUARIOS
        # ----------------------------------------------------

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,

                username TEXT,
                display_name TEXT,

                created_at TEXT,
                joined_at TEXT,

                first_seen TEXT,
                last_seen TEXT,

                messages INTEGER DEFAULT 0,
                characters INTEGER DEFAULT 0,

                attachments INTEGER DEFAULT 0,
                links INTEGER DEFAULT 0,

                reactions_added INTEGER DEFAULT 0,

                messages_deleted INTEGER DEFAULT 0,
                messages_edited INTEGER DEFAULT 0,

                typing_events INTEGER DEFAULT 0,

                voice_sessions INTEGER DEFAULT 0,
                voice_seconds INTEGER DEFAULT 0,

                online_seconds INTEGER DEFAULT 0,
                idle_seconds INTEGER DEFAULT 0,

                last_voice_channel_id INTEGER,
                last_text_channel_id INTEGER,

                PRIMARY KEY (guild_id, user_id)
            )
        """)

        # ----------------------------------------------------
        # MENSAJES
        # ----------------------------------------------------

        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,

                timestamp TEXT NOT NULL,

                characters INTEGER DEFAULT 0,
                attachments INTEGER DEFAULT 0,
                links INTEGER DEFAULT 0
            )
        """)

        # ----------------------------------------------------
        # EVENTOS DE MIEMBROS
        # ----------------------------------------------------

        await db.execute("""
            CREATE TABLE IF NOT EXISTS member_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,

                event TEXT NOT NULL,

                timestamp TEXT NOT NULL
            )
        """)

        # ----------------------------------------------------
        # VOZ
        # ----------------------------------------------------

        await db.execute("""
            CREATE TABLE IF NOT EXISTS voice_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,

                channel_id INTEGER NOT NULL,

                joined_at TEXT NOT NULL,
                left_at TEXT,

                duration_seconds INTEGER DEFAULT 0
            )
        """)

        # ----------------------------------------------------
        # PRESENCIA
        # ----------------------------------------------------

        await db.execute("""
            CREATE TABLE IF NOT EXISTS presence_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,

                status TEXT NOT NULL,

                started_at TEXT NOT NULL,
                ended_at TEXT,

                duration_seconds INTEGER DEFAULT 0
            )
        """)

        # ----------------------------------------------------
        # EVENTOS DE PRESENCIA
        # ----------------------------------------------------

        await db.execute("""
            CREATE TABLE IF NOT EXISTS presence_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,

                status TEXT NOT NULL,

                timestamp TEXT NOT NULL
            )
        """)

        # ----------------------------------------------------
        # REACCIONES
        # ----------------------------------------------------

        await db.execute("""
            CREATE TABLE IF NOT EXISTS reactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,

                channel_id INTEGER,
                message_id INTEGER,

                emoji TEXT,

                timestamp TEXT NOT NULL
            )
        """)

        # ----------------------------------------------------
        # EDICIONES
        # ----------------------------------------------------

        await db.execute("""
            CREATE TABLE IF NOT EXISTS message_edits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,

                channel_id INTEGER,
                message_id INTEGER,

                timestamp TEXT NOT NULL
            )
        """)

        # ----------------------------------------------------
        # BORRADOS
        # ----------------------------------------------------

        await db.execute("""
            CREATE TABLE IF NOT EXISTS message_deletions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                guild_id INTEGER NOT NULL,
                user_id INTEGER,

                channel_id INTEGER,
                message_id INTEGER,

                timestamp TEXT NOT NULL
            )
        """)

        # ----------------------------------------------------
        # ÍNDICES
        # ----------------------------------------------------

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_guild_user
            ON messages(guild_id, user_id)
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp
            ON messages(timestamp)
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_voice_guild_user
            ON voice_sessions(guild_id, user_id)
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_presence_guild_user
            ON presence_sessions(guild_id, user_id)
        """)

        await db.commit()

    print("[STATS][DB] Base de datos lista", flush=True)


# ============================================================
# USER PROFILE
# ============================================================

async def ensure_user(member):

    current = now()

    created_at = getattr(member, "created_at", current)
    joined_at = getattr(member, "joined_at", None)

    await db_execute("""
        INSERT INTO users (
            guild_id,
            user_id,
            username,
            display_name,
            created_at,
            joined_at,
            first_seen,
            last_seen
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(guild_id, user_id)
        DO UPDATE SET
            username = excluded.username,
            display_name = excluded.display_name,
            last_seen = excluded.last_seen
    """, (
        member.guild.id,
        member.id,
        str(member),
        member.display_name,
        iso(created_at),
        iso(joined_at) if joined_at else None,
        iso(current),
        iso(current)
    ))


async def update_last_seen(
    guild_id,
    user_id,
    text_channel_id=None,
    voice_channel_id=None
):

    if text_channel_id is not None:

        await db_execute("""
            UPDATE users
            SET
                last_seen = ?,
                last_text_channel_id = ?
            WHERE guild_id = ?
            AND user_id = ?
        """, (
            iso(),
            text_channel_id,
            guild_id,
            user_id
        ))

    elif voice_channel_id is not None:

        await db_execute("""
            UPDATE users
            SET
                last_seen = ?,
                last_voice_channel_id = ?
            WHERE guild_id = ?
            AND user_id = ?
        """, (
            iso(),
            voice_channel_id,
            guild_id,
            user_id
        ))

    else:

        await db_execute("""
            UPDATE users
            SET last_seen = ?
            WHERE guild_id = ?
            AND user_id = ?
        """, (
            iso(),
            guild_id,
            user_id
        ))


# ============================================================
# READY
# ============================================================

async def stats_on_ready():

    global _initialized

    if _initialized:
        return

    print("[STATS] Inicializando módulo...", flush=True)

    await init_db()

    guild = _client.get_guild(GUILD_ID)

    if guild is None:
        print(
            f"[STATS] ERROR: No se encontró el servidor {GUILD_ID}",
            flush=True
        )
        return

    print(
        f"[STATS] Sincronizando {len(guild.members)} usuarios...",
        flush=True
    )

    for member in guild.members:

        if member.bot:
            continue

        try:
            await ensure_user(member)

        except Exception as e:

            print(
                f"[STATS] Error usuario {member.id}: {e}",
                flush=True
            )

    # --------------------------------------------------------
    # RECUPERAR SESIONES DE VOZ
    # --------------------------------------------------------

    for voice_channel in guild.voice_channels:

        for member in voice_channel.members:

            if member.bot:
                continue

            existing = await db_execute("""
                SELECT id
                FROM voice_sessions
                WHERE guild_id = ?
                AND user_id = ?
                AND left_at IS NULL
                ORDER BY id DESC
                LIMIT 1
            """, (
                guild.id,
                member.id
            ), fetch=True)

            if not existing:

                await db_execute("""
                    INSERT INTO voice_sessions (
                        guild_id,
                        user_id,
                        channel_id,
                        joined_at
                    )
                    VALUES (?, ?, ?, ?)
                """, (
                    guild.id,
                    member.id,
                    voice_channel.id,
                    iso()
                ))

                await db_execute("""
                    UPDATE users
                    SET
                        voice_sessions = voice_sessions + 1,
                        last_voice_channel_id = ?,
                        last_seen = ?
                    WHERE guild_id = ?
                    AND user_id = ?
                """, (
                    voice_channel.id,
                    iso(),
                    guild.id,
                    member.id
                ))

                print(
                    f"[STATS][VOICE] Sesión recuperada: "
                    f"{member} -> {voice_channel.name}",
                    flush=True
                )

    _initialized = True

    print("[STATS] Módulo listo", flush=True)


# ============================================================
# MESSAGE
# ============================================================

async def stats_on_message(message):

    if message.author.bot:
        return

    if message.guild is None:
        return

    if message.guild.id != GUILD_ID:
        return

    content = message.content or ""

    characters = len(content)
    attachments = len(message.attachments)
    links = (
        content.count("http://") +
        content.count("https://")
    )

    try:

        await ensure_user(message.author)

        await db_execute("""
            INSERT INTO messages (
                guild_id,
                user_id,
                channel_id,
                timestamp,
                characters,
                attachments,
                links
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            message.guild.id,
            message.author.id,
            message.channel.id,
            iso(message.created_at),
            characters,
            attachments,
            links
        ))

        await db_execute("""
            UPDATE users
            SET
                messages = messages + 1,
                characters = characters + ?,
                attachments = attachments + ?,
                links = links + ?,
                last_seen = ?,
                last_text_channel_id = ?
            WHERE guild_id = ?
            AND user_id = ?
        """, (
            characters,
            attachments,
            links,
            iso(),
            message.channel.id,
            message.guild.id,
            message.author.id
        ))

        print(
            f"[STATS][MESSAGE] "
            f"{message.guild.name} | "
            f"{message.author} | "
            f"#{message.channel.name}",
            flush=True
        )

    except Exception as e:

        print(
            f"[STATS][MESSAGE] ERROR: "
            f"{type(e).__name__}: {e}",
            flush=True
        )


# ============================================================
# MESSAGE EDIT
# ============================================================

async def stats_on_message_edit(before, after):

    if after.author.bot:
        return

    if after.guild is None:
        return

    if after.guild.id != GUILD_ID:
        return

    try:

        await db_execute("""
            INSERT INTO message_edits (
                guild_id,
                user_id,
                channel_id,
                message_id,
                timestamp
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            after.guild.id,
            after.author.id,
            after.channel.id,
            after.id,
            iso()
        ))

        await db_execute("""
            UPDATE users
            SET
                messages_edited = messages_edited + 1,
                last_seen = ?
            WHERE guild_id = ?
            AND user_id = ?
        """, (
            iso(),
            after.guild.id,
            after.author.id
        ))

    except Exception as e:

        print(
            f"[STATS][EDIT] ERROR: "
            f"{type(e).__name__}: {e}",
            flush=True
        )


# ============================================================
# MESSAGE DELETE
# ============================================================

async def stats_on_message_delete(message):

    if message.guild is None:
        return

    if message.guild.id != GUILD_ID:
        return

    if message.author.bot:
        return

    try:

        await db_execute("""
            INSERT INTO message_deletions (
                guild_id,
                user_id,
                channel_id,
                message_id,
                timestamp
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            message.guild.id,
            message.author.id,
            message.channel.id,
            message.id,
            iso()
        ))

        await db_execute("""
            UPDATE users
            SET messages_deleted = messages_deleted + 1
            WHERE guild_id = ?
            AND user_id = ?
        """, (
            message.guild.id,
            message.author.id
        ))

    except Exception as e:

        print(
            f"[STATS][DELETE] ERROR: "
            f"{type(e).__name__}: {e}",
            flush=True
        )


# ============================================================
# REACTION
# ============================================================

async def stats_on_raw_reaction_add(payload):

    if payload.guild_id is None:
        return

    if payload.guild_id != GUILD_ID:
        return

    guild = _client.get_guild(payload.guild_id)

    if guild is None:
        return

    member = guild.get_member(payload.user_id)

    if member is None or member.bot:
        return

    try:

        await ensure_user(member)

        await db_execute("""
            INSERT INTO reactions (
                guild_id,
                user_id,
                channel_id,
                message_id,
                emoji,
                timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            payload.guild_id,
            payload.user_id,
            payload.channel_id,
            payload.message_id,
            str(payload.emoji),
            iso()
        ))

        await db_execute("""
            UPDATE users
            SET
                reactions_added = reactions_added + 1,
                last_seen = ?
            WHERE guild_id = ?
            AND user_id = ?
        """, (
            iso(),
            payload.guild_id,
            payload.user_id
        ))

    except Exception as e:

        print(
            f"[STATS][REACTION] ERROR: "
            f"{type(e).__name__}: {e}",
            flush=True
        )


# ============================================================
# TYPING
# ============================================================

async def stats_on_typing(channel, user, when):

    if user.bot:
        return

    if channel.guild is None:
        return

    if channel.guild.id != GUILD_ID:
        return

    try:

        await ensure_user(user)

        await db_execute("""
            UPDATE users
            SET
                typing_events = typing_events + 1,
                last_seen = ?,
                last_text_channel_id = ?
            WHERE guild_id = ?
            AND user_id = ?
        """, (
            iso(),
            channel.id,
            channel.guild.id,
            user.id
        ))

    except Exception as e:

        print(
            f"[STATS][TYPING] ERROR: "
            f"{type(e).__name__}: {e}",
            flush=True
        )


# ============================================================
# MEMBER JOIN
# ============================================================

async def stats_on_member_join(member):

    if member.bot:
        return

    if member.guild.id != GUILD_ID:
        return

    try:

        await ensure_user(member)

        await db_execute("""
            INSERT INTO member_events (
                guild_id,
                user_id,
                event,
                timestamp
            )
            VALUES (?, ?, ?, ?)
        """, (
            member.guild.id,
            member.id,
            "join",
            iso()
        ))

        print(
            f"[STATS][MEMBER] JOIN "
            f"{member} -> {member.guild.name}",
            flush=True
        )

    except Exception as e:

        print(
            f"[STATS][JOIN] ERROR: "
            f"{type(e).__name__}: {e}",
            flush=True
        )


# ============================================================
# MEMBER LEAVE
# ============================================================

async def stats_on_member_remove(member):

    if member.guild.id != GUILD_ID:
        return

    try:

        await db_execute("""
            INSERT INTO member_events (
                guild_id,
                user_id,
                event,
                timestamp
            )
            VALUES (?, ?, ?, ?)
        """, (
            member.guild.id,
            member.id,
            "leave",
            iso()
        ))

        print(
            f"[STATS][MEMBER] LEAVE "
            f"{member} -> {member.guild.name}",
            flush=True
        )

    except Exception as e:

        print(
            f"[STATS][LEAVE] ERROR: "
            f"{type(e).__name__}: {e}",
            flush=True
        )


# ============================================================
# VOICE
# ============================================================

async def stats_on_voice_state_update(member, before, after):

    if member.bot:
        return

    if member.guild.id != GUILD_ID:
        return

    guild_id = member.guild.id
    user_id = member.id

    try:

        await ensure_user(member)

        # ----------------------------------------------------
        # JOIN
        # ----------------------------------------------------

        if before.channel is None and after.channel is not None:

            await db_execute("""
                INSERT INTO voice_sessions (
                    guild_id,
                    user_id,
                    channel_id,
                    joined_at
                )
                VALUES (?, ?, ?, ?)
            """, (
                guild_id,
                user_id,
                after.channel.id,
                iso()
            ))

            await db_execute("""
                UPDATE users
                SET
                    voice_sessions = voice_sessions + 1,
                    last_seen = ?,
                    last_voice_channel_id = ?
                WHERE guild_id = ?
                AND user_id = ?
            """, (
                iso(),
                after.channel.id,
                guild_id,
                user_id
            ))

            print(
                f"[STATS][VOICE] JOIN "
                f"{member} -> {after.channel.name}",
                flush=True
            )

        # ----------------------------------------------------
        # LEAVE
        # ----------------------------------------------------

        elif before.channel is not None and after.channel is None:

            current = now()

            session = await db_execute("""
                SELECT id, joined_at
                FROM voice_sessions
                WHERE guild_id = ?
                AND user_id = ?
                AND left_at IS NULL
                ORDER BY id DESC
                LIMIT 1
            """, (
                guild_id,
                user_id
            ), fetch=True)

            if session:

                session_id, joined_at = session

                joined = parse_time(joined_at)

                duration = 0

                if joined:
                    duration = int(
                        (current - joined).total_seconds()
                    )

                await db_execute("""
                    UPDATE voice_sessions
                    SET
                        left_at = ?,
                        duration_seconds = ?
                    WHERE id = ?
                """, (
                    iso(current),
                    duration,
                    session_id
                ))

                await db_execute("""
                    UPDATE users
                    SET
                        voice_seconds = voice_seconds + ?,
                        last_seen = ?
                    WHERE guild_id = ?
                    AND user_id = ?
                """, (
                    duration,
                    iso(current),
                    guild_id,
                    user_id
                ))

            print(
                f"[STATS][VOICE] LEAVE "
                f"{member} <- {before.channel.name}",
                flush=True
            )

        # ----------------------------------------------------
        # MOVE
        # ----------------------------------------------------

        elif (
            before.channel is not None
            and after.channel is not None
            and before.channel.id != after.channel.id
        ):

            current = now()

            session = await db_execute("""
                SELECT id, joined_at
                FROM voice_sessions
                WHERE guild_id = ?
                AND user_id = ?
                AND left_at IS NULL
                ORDER BY id DESC
                LIMIT 1
            """, (
                guild_id,
                user_id
            ), fetch=True)

            if session:

                session_id, joined_at = session

                joined = parse_time(joined_at)

                duration = 0

                if joined:
                    duration = int(
                        (current - joined).total_seconds()
                    )

                await db_execute("""
                    UPDATE voice_sessions
                    SET
                        left_at = ?,
                        duration_seconds = ?
                    WHERE id = ?
                """, (
                    iso(current),
                    duration,
                    session_id
                ))

                await db_execute("""
                    UPDATE users
                    SET
                        voice_seconds = voice_seconds + ?,
                        last_seen = ?,
                        last_voice_channel_id = ?
                    WHERE guild_id = ?
                    AND user_id = ?
                """, (
                    duration,
                    iso(current),
                    after.channel.id,
                    guild_id,
                    user_id
                ))

            await db_execute("""
                INSERT INTO voice_sessions (
                    guild_id,
                    user_id,
                    channel_id,
                    joined_at
                )
                VALUES (?, ?, ?, ?)
            """, (
                guild_id,
                user_id,
                after.channel.id,
                iso(current)
            ))

            print(
                f"[STATS][VOICE] MOVE "
                f"{member}: "
                f"{before.channel.name} -> "
                f"{after.channel.name}",
                flush=True
            )

        # ----------------------------------------------------
        # OTROS CAMBIOS
        # ----------------------------------------------------

        else:

            await update_last_seen(
                guild_id,
                user_id,
                voice_channel_id=(
                    after.channel.id
                    if after.channel
                    else None
                )
            )

    except Exception as e:

        print(
            f"[STATS][VOICE] ERROR: "
            f"{type(e).__name__}: {e}",
            flush=True
        )


# ============================================================
# PRESENCE
# ============================================================

async def stats_on_presence_update(before, after):

    if after.bot:
        return

    if after.guild is None:
        return

    if after.guild.id != GUILD_ID:
        return

    guild_id = after.guild.id
    user_id = after.id

    try:

        before_status = str(before.status)
        after_status = str(after.status)

        if before_status == after_status:
            return

        current = now()

        previous = await db_execute("""
            SELECT id, started_at, status
            FROM presence_sessions
            WHERE guild_id = ?
            AND user_id = ?
            AND ended_at IS NULL
            ORDER BY id DESC
            LIMIT 1
        """, (
            guild_id,
            user_id
        ), fetch=True)

        if previous:

            session_id, started_at, status = previous

            started = parse_time(started_at)

            duration = 0

            if started:
                duration = int(
                    (current - started).total_seconds()
                )

            await db_execute("""
                UPDATE presence_sessions
                SET
                    ended_at = ?,
                    duration_seconds = ?
                WHERE id = ?
            """, (
                iso(current),
                duration,
                session_id
            ))

            if status == "online":

                await db_execute("""
                    UPDATE users
                    SET online_seconds =
                        online_seconds + ?
                    WHERE guild_id = ?
                    AND user_id = ?
                """, (
                    duration,
                    guild_id,
                    user_id
                ))

            elif status == "idle":

                await db_execute("""
                    UPDATE users
                    SET idle_seconds =
                        idle_seconds + ?
                    WHERE guild_id = ?
                    AND user_id = ?
                """, (
                    duration,
                    guild_id,
                    user_id
                ))

        await ensure_user(after)

        await db_execute("""
            INSERT INTO presence_sessions (
                guild_id,
                user_id,
                status,
                started_at
            )
            VALUES (?, ?, ?, ?)
        """, (
            guild_id,
            user_id,
            after_status,
            iso(current)
        ))

        await db_execute("""
            INSERT INTO presence_events (
                guild_id,
                user_id,
                status,
                timestamp
            )
            VALUES (?, ?, ?, ?)
        """, (
            guild_id,
            user_id,
            after_status,
            iso(current)
        ))

        await update_last_seen(
            guild_id,
            user_id
        )

    except Exception as e:

        print(
            f"[STATS][PRESENCE] ERROR: "
            f"{type(e).__name__}: {e}",
            flush=True
        )


# ============================================================
# /STATS
# ============================================================

@app_commands.command(
    name="stats",
    description="Estadísticas completas del servidor"
)
async def stats(interaction: discord.Interaction):

    print(
        "[STATS] /stats recibido",
        flush=True
    )

    if interaction.guild is None:

        await interaction.response.send_message(
            "❌ Este comando solo funciona dentro de un servidor.",
            ephemeral=True
        )

        return

    if interaction.guild.id != GUILD_ID:

        await interaction.response.send_message(
            "❌ Este comando no está disponible en este servidor.",
            ephemeral=True
        )

        return

    try:

        await interaction.response.defer()

        guild = interaction.guild

        # ====================================================
        # GENERAL
        # ====================================================

        result = await db_execute("""
            SELECT COUNT(*)
            FROM messages
            WHERE guild_id = ?
        """, (guild.id,), fetch=True)

        total_messages = result[0]

        result = await db_execute("""
            SELECT COALESCE(SUM(characters), 0)
            FROM messages
            WHERE guild_id = ?
        """, (guild.id,), fetch=True)

        total_characters = result[0]

        result = await db_execute("""
            SELECT COUNT(*)
            FROM messages
            WHERE guild_id = ?
            AND timestamp >= ?
        """, (
            guild.id,
            iso(now() - timedelta(days=7))
        ), fetch=True)

        weekly_messages = result[0]

        result = await db_execute("""
            SELECT COUNT(*)
            FROM messages
            WHERE guild_id = ?
            AND timestamp >= ?
        """, (
            guild.id,
            iso(now() - timedelta(days=30))
        ), fetch=True)

        monthly_messages = result[0]

        # ====================================================
        # VOZ
        # ====================================================

        result = await db_execute("""
            SELECT COALESCE(SUM(duration_seconds), 0)
            FROM voice_sessions
            WHERE guild_id = ?
        """, (guild.id,), fetch=True)

        total_voice = result[0]

        # ====================================================
        # ACTIVIDAD
        # ====================================================

        result = await db_execute("""
            SELECT COUNT(*)
            FROM users
            WHERE guild_id = ?
            AND messages > 0
        """, (guild.id,), fetch=True)

        active_users = result[0]

        # ====================================================
        # TOP USUARIOS
        # ====================================================

        top_users = await db_execute("""
            SELECT
                user_id,
                messages,
                characters,
                voice_seconds
            FROM users
            WHERE guild_id = ?
            ORDER BY messages DESC
            LIMIT 10
        """, (guild.id,), fetchall=True)

        # ====================================================
        # TOP VOZ
        # ====================================================

        top_voice = await db_execute("""
            SELECT
                user_id,
                voice_seconds
            FROM users
            WHERE guild_id = ?
            ORDER BY voice_seconds DESC
            LIMIT 10
        """, (guild.id,), fetchall=True)

        # ====================================================
        # TOP CANALES
        # ====================================================

        top_channels = await db_execute("""
            SELECT
                channel_id,
                COUNT(*) AS total
            FROM messages
            WHERE guild_id = ?
            GROUP BY channel_id
            ORDER BY total DESC
            LIMIT 10
        """, (guild.id,), fetchall=True)

        # ====================================================
        # HORA
        # ====================================================

        busiest_hour = await db_execute("""
            SELECT
                strftime('%H', timestamp),
                COUNT(*)
            FROM messages
            WHERE guild_id = ?
            GROUP BY strftime('%H', timestamp)
            ORDER BY COUNT(*) DESC
            LIMIT 1
        """, (guild.id,), fetch=True)

        # ====================================================
        # DÍA
        # ====================================================

        busiest_day = await db_execute("""
            SELECT
                strftime('%w', timestamp),
                COUNT(*)
            FROM messages
            WHERE guild_id = ?
            GROUP BY strftime('%w', timestamp)
            ORDER BY COUNT(*) DESC
            LIMIT 1
        """, (guild.id,), fetch=True)

        # ====================================================
        # ENTRADAS / SALIDAS
        # ====================================================

        result = await db_execute("""
            SELECT COUNT(*)
            FROM member_events
            WHERE guild_id = ?
            AND event = 'join'
        """, (guild.id,), fetch=True)

        joins = result[0]

        result = await db_execute("""
            SELECT COUNT(*)
            FROM member_events
            WHERE guild_id = ?
            AND event = 'leave'
        """, (guild.id,), fetch=True)

        leaves = result[0]

        # ====================================================
        # EMBED
        # ====================================================

        embed = discord.Embed(
            title=f"📊 Estadísticas globales — {guild.name}",
            description=(
                "Estadísticas recopiladas por el bot "
                "sobre la actividad del servidor."
            ),
            color=discord.Color.blurple(),
            timestamp=now()
        )

        bots = sum(
            1
            for member in guild.members
            if member.bot
        )

        embed.add_field(
            name="👥 Miembros",
            value=f"{guild.member_count:,}",
            inline=True
        )

        embed.add_field(
            name="🤖 Bots",
            value=f"{bots:,}",
            inline=True
        )

        embed.add_field(
            name="🟢 Usuarios activos",
            value=f"{active_users:,}",
            inline=True
        )

        embed.add_field(
            name="💬 Mensajes totales",
            value=f"{total_messages:,}",
            inline=True
        )

        embed.add_field(
            name="📅 Últimos 7 días",
            value=f"{weekly_messages:,}",
            inline=True
        )

        embed.add_field(
            name="📆 Últimos 30 días",
            value=f"{monthly_messages:,}",
            inline=True
        )

        embed.add_field(
            name="📝 Caracteres escritos",
            value=f"{total_characters:,}",
            inline=True
        )

        embed.add_field(
            name="🎙️ Tiempo en voz",
            value=format_duration(total_voice),
            inline=True
        )

        embed.add_field(
            name="📥 Entradas",
            value=f"{joins:,}",
            inline=True
        )

        embed.add_field(
            name="📤 Salidas",
            value=f"{leaves:,}",
            inline=True
        )

        if busiest_hour:

            embed.add_field(
                name="⏰ Hora más activa",
                value=(
                    f"{busiest_hour[0]}:00 "
                    f"({busiest_hour[1]:,} mensajes)"
                ),
                inline=False
            )

        if busiest_day:

            days = {
                "0": "Domingo",
                "1": "Lunes",
                "2": "Martes",
                "3": "Miércoles",
                "4": "Jueves",
                "5": "Viernes",
                "6": "Sábado"
            }

            day_name = days.get(
                str(busiest_day[0]),
                "Desconocido"
            )

            embed.add_field(
                name="📅 Día más activo",
                value=(
                    f"{day_name} "
                    f"({busiest_day[1]:,} mensajes)"
                ),
                inline=False
            )

        # ====================================================
        # TOP MENSAJES
        # ====================================================

        if top_users:

            ranking = []

            for position, (
                user_id,
                messages,
                characters,
                voice_seconds
            ) in enumerate(top_users, start=1):

                member = guild.get_member(user_id)

                if member:

                    ranking.append(
                        f"**{position}.** "
                        f"{member.mention} — "
                        f"💬 {messages:,} "
                        f"· 📝 {characters:,}"
                    )

            if ranking:

                embed.add_field(
                    name="🏆 Usuarios más activos",
                    value="\n".join(ranking),
                    inline=False
                )

        # ====================================================
        # TOP VOZ
        # ====================================================

        if top_voice:

            ranking = []

            for position, (
                user_id,
                seconds
            ) in enumerate(top_voice, start=1):

                member = guild.get_member(user_id)

                if member:

                    ranking.append(
                        f"**{position}.** "
                        f"{member.mention} — "
                        f"{format_duration(seconds)}"
                    )

            if ranking:

                embed.add_field(
                    name="🎙️ Más tiempo en voz",
                    value="\n".join(ranking),
                    inline=False
                )

        # ====================================================
        # TOP CANALES
        # ====================================================

        if top_channels:

            ranking = []

            for position, (
                channel_id,
                total
            ) in enumerate(top_channels, start=1):

                channel = guild.get_channel(channel_id)

                if channel:

                    ranking.append(
                        f"**{position}.** "
                        f"{channel.mention} — "
                        f"{total:,} mensajes"
                    )

            if ranking:

                embed.add_field(
                    name="💬 Canales más activos",
                    value="\n".join(ranking),
                    inline=False
                )

        embed.set_footer(
            text="Sistema global de estadísticas"
        )

        await interaction.followup.send(
            embed=embed
        )

        print(
            "[STATS] Estadísticas enviadas correctamente",
            flush=True
        )

    except Exception as e:

        print(
            f"[STATS] ERROR: "
            f"{type(e).__name__}: {e}",
            flush=True
        )

        try:

            await interaction.followup.send(
                "❌ Error generando las estadísticas.",
                ephemeral=True
            )

        except Exception as followup_error:

            print(
                f"[STATS] FOLLOWUP ERROR: "
                f"{type(followup_error).__name__}: "
                f"{followup_error}",
                flush=True
            )


# ============================================================
# /USERSTATS
# ============================================================

@app_commands.command(
    name="userstats",
    description="Muestra las estadísticas completas de un usuario"
)
@app_commands.describe(
    member="Usuario del que quieres ver las estadísticas"
)
async def userstats(
    interaction: discord.Interaction,
    member: discord.Member = None
):

    if interaction.guild is None:

        await interaction.response.send_message(
            "❌ Solo puedes usar este comando en un servidor.",
            ephemeral=True
        )

        return

    if interaction.guild.id != GUILD_ID:

        await interaction.response.send_message(
            "❌ Este comando no está disponible en este servidor.",
            ephemeral=True
        )

        return

    if member is None:
        member = interaction.user

    if member.bot:

        await interaction.response.send_message(
            "❌ No se recopilan estadísticas de bots.",
            ephemeral=True
        )

        return

    await interaction.response.defer()

    try:

        await ensure_user(member)

        data = await db_execute("""
            SELECT
                messages,
                characters,
                attachments,
                links,
                reactions_added,
                messages_deleted,
                messages_edited,
                typing_events,
                voice_sessions,
                voice_seconds,
                online_seconds,
                idle_seconds,
                created_at,
                joined_at,
                first_seen,
                last_seen
            FROM users
            WHERE guild_id = ?
            AND user_id = ?
        """, (
            interaction.guild.id,
            member.id
        ), fetch=True)

        if not data:

            await interaction.followup.send(
                "No hay estadísticas para este usuario."
            )

            return

        (
            messages,
            characters,
            attachments,
            links,
            reactions,
            deleted,
            edited,
            typing,
            voice_sessions,
            voice_seconds,
            online_seconds,
            idle_seconds,
            created_at,
            joined_at,
            first_seen,
            last_seen
        ) = data

        # ----------------------------------------------------
        # RANK
        # ----------------------------------------------------

        rank_data = await db_execute("""
            SELECT COUNT(*) + 1
            FROM users
            WHERE guild_id = ?
            AND messages > ?
        """, (
            interaction.guild.id,
            messages
        ), fetch=True)

        rank = rank_data[0]

        # ----------------------------------------------------
        # CANAL FAVORITO
        # ----------------------------------------------------

        favorite_channel = await db_execute("""
            SELECT
                channel_id,
                COUNT(*)
            FROM messages
            WHERE guild_id = ?
            AND user_id = ?
            GROUP BY channel_id
            ORDER BY COUNT(*) DESC
            LIMIT 1
        """, (
            interaction.guild.id,
            member.id
        ), fetch=True)

        favorite_channel_text = "Ninguno"

        if favorite_channel:

            channel = interaction.guild.get_channel(
                favorite_channel[0]
            )

            if channel:

                favorite_channel_text = (
                    f"{channel.mention} "
                    f"({favorite_channel[1]:,} mensajes)"
                )

        # ----------------------------------------------------
        # HORA FAVORITA
        # ----------------------------------------------------

        favorite_hour = await db_execute("""
            SELECT
                strftime('%H', timestamp),
                COUNT(*)
            FROM messages
            WHERE guild_id = ?
            AND user_id = ?
            GROUP BY strftime('%H', timestamp)
            ORDER BY COUNT(*) DESC
            LIMIT 1
        """, (
            interaction.guild.id,
            member.id
        ), fetch=True)

        favorite_hour_text = "N/A"

        if favorite_hour:
            favorite_hour_text = f"{favorite_hour[0]}:00"

        # ----------------------------------------------------
        # EMBED
        # ----------------------------------------------------

        embed = discord.Embed(
            title=f"👤 Estadísticas de {member.display_name}",
            color=discord.Color.blurple(),
            timestamp=now()
        )

        if member.avatar:

            embed.set_thumbnail(
                url=member.avatar.url
            )

        embed.add_field(
            name="💬 Mensajes",
            value=f"{messages:,}",
            inline=True
        )

        embed.add_field(
            name="📝 Caracteres",
            value=f"{characters:,}",
            inline=True
        )

        embed.add_field(
            name="🏆 Ranking",
            value=f"#{rank}",
            inline=True
        )

        embed.add_field(
            name="📎 Adjuntos",
            value=f"{attachments:,}",
            inline=True
        )

        embed.add_field(
            name="🔗 Enlaces",
            value=f"{links:,}",
            inline=True
        )

        embed.add_field(
            name="😀 Reacciones",
            value=f"{reactions:,}",
            inline=True
        )

        embed.add_field(
            name="✏️ Mensajes editados",
            value=f"{edited:,}",
            inline=True
        )

        embed.add_field(
            name="🗑️ Mensajes borrados",
            value=f"{deleted:,}",
            inline=True
        )

        embed.add_field(
            name="⌨️ Eventos de escritura",
            value=f"{typing:,}",
            inline=True
        )

        embed.add_field(
            name="🎙️ Sesiones de voz",
            value=f"{voice_sessions:,}",
            inline=True
        )

        embed.add_field(
            name="🔊 Tiempo en voz",
            value=format_duration(voice_seconds),
            inline=True
        )

        embed.add_field(
            name="🟢 Tiempo online detectado",
            value=format_duration(online_seconds),
            inline=True
        )

        embed.add_field(
            name="💤 Tiempo idle detectado",
            value=format_duration(idle_seconds),
            inline=True
        )

        embed.add_field(
            name="📢 Canal favorito",
            value=favorite_channel_text,
            inline=False
        )

        embed.add_field(
            name="⏰ Hora favorita",
            value=favorite_hour_text,
            inline=True
        )

        # ----------------------------------------------------
        # FECHAS
        # ----------------------------------------------------

        joined_text = "Desconocido"

        if joined_at:

            joined = parse_time(joined_at)

            if joined:

                days = (
                    now() - joined
                ).days

                joined_text = (
                    f"<t:{int(joined.timestamp())}:D>\n"
                    f"({days:,} días)"
                )

        created_text = "Desconocido"

        if created_at:

            created = parse_time(created_at)

            if created:

                created_text = (
                    f"<t:{int(created.timestamp())}:D>"
                )

        last_seen_text = "Nunca"

        if last_seen:

            last = parse_time(last_seen)

            if last:

                last_seen_text = (
                    f"<t:{int(last.timestamp())}:R>"
                )

        embed.add_field(
            name="📥 Entró al servidor",
            value=joined_text,
            inline=True
        )

        embed.add_field(
            name="🆔 Cuenta creada",
            value=created_text,
            inline=True
        )

        embed.add_field(
            name="👀 Última actividad",
            value=last_seen_text,
            inline=True
        )

        # ----------------------------------------------------
        # ROLES
        # ----------------------------------------------------

        roles = [
            role.mention
            for role in member.roles
            if role != interaction.guild.default_role
        ]

        if roles:

            roles_text = ", ".join(roles)

            if len(roles_text) > 1000:
                roles_text = roles_text[:997] + "..."

            embed.add_field(
                name="🏷️ Roles",
                value=roles_text,
                inline=False
            )

        embed.set_footer(
            text="Estadísticas individuales"
        )

        await interaction.followup.send(
            embed=embed
        )

    except Exception as e:

        print(
            f"[USERSTATS] ERROR: "
            f"{type(e).__name__}: {e}",
            flush=True
        )

        try:

            await interaction.followup.send(
                "❌ Error generando las estadísticas.",
                ephemeral=True
            )

        except Exception:
            pass


# ============================================================
# SETUP
# ============================================================

def setup_stats(client):

    global _client

    if _client is not None:
        print("[STATS] Módulo ya cargado", flush=True)
        return

    _client = client

    print("[STATS] Registrando módulo...", flush=True)

    # --------------------------------------------------------
    # COMANDOS
    # --------------------------------------------------------

    client.tree.add_command(
        stats,
        guild=GUILD
    )

    client.tree.add_command(
        userstats,
        guild=GUILD
    )

    # --------------------------------------------------------
    # EVENTOS
    # --------------------------------------------------------

    client.add_listener(
        stats_on_ready,
        "on_ready"
    )

    client.add_listener(
        stats_on_message,
        "on_message"
    )

    client.add_listener(
        stats_on_message_edit,
        "on_message_edit"
    )

    client.add_listener(
        stats_on_message_delete,
        "on_message_delete"
    )

    client.add_listener(
        stats_on_raw_reaction_add,
        "on_raw_reaction_add"
    )

    client.add_listener(
        stats_on_typing,
        "on_typing"
    )

    client.add_listener(
        stats_on_member_join,
        "on_member_join"
    )

    client.add_listener(
        stats_on_member_remove,
        "on_member_remove"
    )

    client.add_listener(
        stats_on_voice_state_update,
        "on_voice_state_update"
    )

    client.add_listener(
        stats_on_presence_update,
        "on_presence_update"
    )

    print("[STATS] Módulo registrado correctamente", flush=True)