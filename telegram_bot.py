import logging, json, time, psutil, asyncio
from datetime import datetime, timedelta
from collections import defaultdict
from telegram import Update, ChatPermissions
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = os.getenv("ADMIN_IDS")
USER_FILE = os.getenv("USER_FILE")
GROUP_FILE = os.getenv("GROUP_FILE")
START_TIME = time.time() 
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS").split(",")]
# ======== JSON HELPERS ========
def load_json(filename, default):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except:
        return default

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f)

USERS = load_json(USER_FILE, {})
ACTIVE_GROUPS = load_json(GROUP_FILE, [])
WARNINGS = defaultdict(int)
LOCKED_CHATS = set()

async def unauthorized(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ admins only")

# ======== LOGGING ========
logging.basicConfig(
    filename="bot_log.txt",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ======== UTILITIES ========
def save_users(): save_json(USER_FILE, USERS)
def save_groups(): save_json(GROUP_FILE, ACTIVE_GROUPS)
def group_allowed(chat_id): return chat_id in ACTIVE_GROUPS
def is_admin(uid): 
    return any(int(uid) == int(admin) for admin in ADMIN_IDS)

def get_uptime():
    delta = int(time.time() - START_TIME)
    hrs, rem = divmod(delta, 3600)
    mins, _ = divmod(rem, 60)
    return f"{hrs}h {mins}m"
# ======== GROUP CHECK DECORATOR ========
def active_group_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat = update.effective_chat

        # Allow private chats
        if chat.type != "private" and chat.id not in ACTIVE_GROUPS:
            try:
                await update.message.delete()
            except Exception as e:
                logging.warning(f"Failed to delete message in inactive group {chat.id}: {e}")

            await context.bot.send_message(
                chat_id=chat.id,
                text="🚫 This group is not activated!\nPlease contact the developer to activate it. @Derexel",
            )
            return

        return await func(update, context, *args, **kwargs)

    return wrapper

# ======== GROUP CHECK ========
async def group_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat

    # Allow private chats
    if chat.type == "private":
        return True

    # If group is not active
    if not group_allowed(chat.id):
        try:
            # Delete the user's message
            await update.message.delete()
        except Exception as e:
            logging.warning(f"Failed to delete message in inactive group {chat.id}: {e}")

        # Notify the group that it is inactive
        await context.bot.send_message(
            chat_id=chat.id,
            text="🚫 This group is not activated!\nPlease contact the developer to activate it.",
        )
        return False

    return True

# ======== COMMANDS ========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await group_check(update, context): return
    user = update.effective_user
    USERS[str(user.id)] = {"name": user.full_name, "last": time.time()}
    save_users()
    await update.message.reply_text(f"👋 Hello {user.first_name}! Type /help for commands.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_admin_user = is_admin(update.effective_user.id)
    text = (
        "📚 *Commands:*\n"
        "/start — Register\n"
        "/help — Show help\n"
        "/getmyid — Show your ID\n"
        "/getmyinfo — Detailed user info\n"
        "/userinfo — Info about replied user\n"
        "/report <text> — Report an issue\n"
        "/feedback <text> — Send feedback\n"
        "/about — About this bot\n"
        "/time — Show server time\n"
        "/rules — Group rules\n"
    )
    if is_admin_user:
        text += (
            "\n🛡 *Admin Commands:*\n"
            "/ban <id> | /unban <id>\n"
            "/mute <id> | /unmute <id>\n"
            "/lock | /unlock\n"
            "/broadcast <msg>\n"
            "/groupinfo | /addgroup | /removegroup <id> | /groups\n"
            "/stats | /listusers | /cleanup | /uptime"
        )
    await update.message.reply_text(text, parse_mode="Markdown")
@active_group_only
async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    # Only allow private chats or active groups
    if chat.type != "private" and chat.id not in ACTIVE_GROUPS:
        return  # Do nothing in inactive groups
    await update.message.reply_text(
        "🤖 Bot by *Derexel* | Powered by `python-telegram-bot`.",
        parse_mode="Markdown"
    )
@active_group_only
async def time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type != "private" and chat.id not in ACTIVE_GROUPS:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await update.message.reply_text(f"🕒 Current Time: {now}")

@active_group_only
async def get_my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type != "private" and chat.id not in ACTIVE_GROUPS:
        return
    await update.message.reply_text(f"🆔 Your ID: {update.effective_user.id}")
@active_group_only
async def get_my_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type != "private" and chat.id not in ACTIVE_GROUPS:
        return
    msg = update.message
    user = msg.reply_to_message.from_user if msg.reply_to_message else update.effective_user
    username = f"@{user.username}" if user.username else "N/A"
    admin_text = "✅ Yes" if is_admin(user.id) else "❌ No"
    await msg.reply_text(
        f"🧾 *User Info:*\n"
        f"👤 Name: {user.full_name}\n"
        f"🆔 ID: {user.id}\n"
        f"🏷 Username: {username}\n"
        f"👮 Admin: {admin_text}\n"
        f"🤖 Bot Account: {user.is_bot}",
        parse_mode="Markdown"
    )


# ======== GROUP MANAGEMENT ========

async def removegroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return await unauthorized(update, context)
    if not context.args: return await update.message.reply_text("Usage: /removegroup <group_id>")
    gid = int(context.args[0])
    if gid in ACTIVE_GROUPS:
        ACTIVE_GROUPS.remove(gid)
        save_groups()
        await update.message.reply_text(f"🗑 Removed group `{gid}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Group not found.")

@active_group_only
async def groupinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return await unauthorized(update, context)
    chat = update.effective_chat
    member_count = await context.bot.get_chat_member_count(chat.id)
    await update.message.reply_text(
        f"📄 *Group Info:*\n"
        f"📛 Name: {chat.title}\n"
        f"🆔 ID: `{chat.id}`\n"
        f"👥 Members: {member_count}\n"
        f"⚙️ Status: {'✅ Active' if group_allowed(chat.id) else '❌ Inactive'}",
        parse_mode="Markdown"
    )

# ======== WELCOME MESSAGE ========
@active_group_only
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    chat_title = chat.title
    chat_id = chat.id

    for member in update.message.new_chat_members:
        user_name = member.full_name
        user_id = member.id

        welcome_text = (
            f"👋 *Welcome {user_name}!*\n"
            f"🎯 Group: {chat_title}\n"
            f"🆔 Group ID: `{chat_id}`\n"
            f"👤 Your ID: `{user_id}`\n\n"
            f"💡 Type /help to see available commands.\n\n"
            f"❤️ *Support the Bot:*\n"
            f"Running this bot costs hosting and maintenance fees.\n"
            f"If you’d like to support, you can donate via TON Wallet 👇\n\n"
            f"💎 *TON Wallet:* `UQCl0noouz_kOdFV5KIbVveZvLgd_yQpP9vPf0adnDxho8o5`"
        )

        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Contact Admin", url="https://t.me/Derexel")]
        ])

        await update.message.reply_text(
            welcome_text,
            parse_mode="Markdown",
            reply_markup=buttons
        )

# ======== USER INFO ========
@active_group_only
async def userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user info (works when replying to a message or standalone)."""
    msg = update.message
    chat = update.effective_chat

    # Allow in private or active groups only
    if chat.type != "private":
        if not await group_check(update, context):
            return

    # Target user
    if msg.reply_to_message:
        target = msg.reply_to_message.from_user
    else:
        target = update.effective_user

    username = f"@{target.username}" if target.username else "N/A"
    is_admin_text = "✅ Yes" if is_admin(target.id) else "❌ No"

    await msg.reply_text(
        f"👤 *User Info:*\n"
        f"👨‍💼 Name: {target.full_name}\n"
        f"🏷 Username: {username}\n"
        f"🆔 ID: `{target.id}`\n"
        f"👮 Admin: {is_admin_text}\n"
        f"🤖 Bot: {target.is_bot}",
        parse_mode="Markdown"
    )


# ======== GROUP MANAGEMENT ========
async def addgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Activate the current group to allow bot commands"""
    user = update.effective_user
    chat = update.effective_chat

    if chat.type not in ["supergroup", "group"]:
        return await update.message.reply_text("❌ This command can only be used in groups.")

    if not is_admin(user.id):
        return await unauthorized(update, context)

    if chat.id not in ACTIVE_GROUPS:
        ACTIVE_GROUPS.append(chat.id)
        save_groups()
        await update.message.reply_text(
            f"✅ *Group added to active list!*\n"
            f"📄 {chat.title}\n"
            f"🆔 `{chat.id}`",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("ℹ️ This group is already active.", parse_mode="Markdown")


async def groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List active groups"""
    user = update.effective_user
    if not is_admin(user.id):
        return await unauthorized(update, context)

    bot = context.bot
    active_text = ""

    for gid in ACTIVE_GROUPS:
        try:
            chat = await bot.get_chat(gid)
            active_text += f"✅ {chat.title} (`{gid}`)\n"
        except Exception:
            active_text += f"⚠️ Unknown Group (`{gid}`)\n"

    text = (
        f"📋 *Groups Information:*\n\n"
        f"✅ *Active Groups:*\n{active_text or 'None'}"
    )

    await update.message.reply_text(text, parse_mode="Markdown")


# ======== REPORT & FEEDBACK ========
@active_group_only
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send report to all admins"""
    if not await group_check(update, context):
        return
    if not context.args:
        return await update.message.reply_text("Usage: /report <your message>")

    report_text = " ".join(context.args)
    user = update.effective_user

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"🚨 *Report from:* {user.full_name}\n🆔 `{user.id}`\n\n💬 {report_text}",
                parse_mode="Markdown"
            )
        except:
            pass

    await update.message.reply_text("✅ Report sent to admin. Thanks!")

@active_group_only
async def feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send feedback to all admins"""
    if not await group_check(update, context):
        return
    if not context.args:
        return await update.message.reply_text("Usage: /feedback <your feedback>")

    text = " ".join(context.args)
    user = update.effective_user

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"💬 *Feedback from:* {user.full_name}\n🆔 `{user.id}`\n\n{text}",
                parse_mode="Markdown"
            )
        except:
            pass

    await update.message.reply_text("✅ Feedback submitted!")


# ======== ADMIN PROTECTION ========
async def unauthorized(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unauthorized command attempts"""
    user = update.effective_user
    chat = update.effective_chat
    message = update.message

    # Try to delete the message
    if message:
        try:
            await message.delete()
        except Exception as e:
            logging.warning(f"Failed to delete unauthorized message: {e}")

    username = f"@{user.username}" if user.username else "N/A"
    chat_info = f"\n🏠 Chat: {chat.title or 'Private Chat'}\n💬 Chat ID: `{chat.id}`"

    alert_text = (
        f"🚫 *Unauthorized Command Attempt!*\n\n"
        f"👤 *User:* {user.full_name}\n"
        f"🆔 *User ID:* `{user.id}`\n"
        f"🏷 *Username:* {username}"
        f"{chat_info}\n"
        f"⏰ *Time:* `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=alert_text,
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Failed to send unauthorized alert to admin {admin_id}: {e}")


# ====== BAN / UNBAN / MUTE / UNMUTE ======
@active_group_only
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check if the sender is a bot administrator
    if not is_admin(user_id):
        return await unauthorized(update, context)

    chat = update.effective_chat
    target_id = None
    target_name = "User"

    # Case 1: Reply to a message
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        target_name = update.message.reply_to_message.from_user.full_name
    
    # Case 2: Using ID after the command /ban 12345
    elif context.args:
        try:
            target_id = int(context.args[0])
        except (ValueError, IndexError):
            return await update.message.reply_text("❌ Invalid format. Use: `/ban <ID>` or reply to a message.")

    if not target_id:
        return await update.message.reply_text("❓ Please reply to the user you want to ban or provide their ID.")

    # Prevent banning other bot developers
    if is_admin(target_id):
        return await update.message.reply_text("🛡️ You cannot ban another bot administrator.")

    try:
        await context.bot.ban_chat_member(chat.id, target_id)
        await update.message.reply_text(
            f"🔨 *User Banned Successfully*\n"
            f"👤 Name: {target_name}\n"
            f"🆔 ID: `{target_id}`", 
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Ban failed. Make sure the bot is an admin in this group and has ban permissions.\n"
            f"Error: {e}"
        )

# ====== BAN / UNBAN / MUTE / UNMUTE ======
@active_group_only
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not group_allowed(update.effective_chat.id):
        return await update.message.reply_text("🚫 Unauthorized group.")
    if not is_admin(update.effective_user.id):
        return await unauthorized(update, context)

    if not context.args:
        return await update.message.reply_text("Usage: /ban <user_id>")

    uid = int(context.args[0])
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, uid)
        await update.message.reply_text(f"🚫 User {uid} banned successfully.")
        logging.info(f"User {uid} banned in {update.effective_chat.title}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error banning user: {e}")

@active_group_only
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not group_allowed(update.effective_chat.id):
        return await update.message.reply_text("🚫 Unauthorized group.")
    if not is_admin(update.effective_user.id):
        return await unauthorized(update, context)

    if not context.args:
        return await update.message.reply_text("Usage: /unban <user_id>")

    uid = int(context.args[0])
    try:
        await context.bot.unban_chat_member(update.effective_chat.id, uid)
        await update.message.reply_text(f"✅ User {uid} unbanned.")
        logging.info(f"User {uid} unbanned in {update.effective_chat.title}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error unbanning user: {e}")

@active_group_only
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not group_allowed(update.effective_chat.id):
        return await update.message.reply_text("🚫 Unauthorized group.")
    if not is_admin(update.effective_user.id):
        return await unauthorized(update, context)
    if not context.args:
        return await update.message.reply_text("Usage: /mute <user_id>")

    uid = int(context.args[0])
    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id, uid,
            permissions=ChatPermissions(can_send_messages=False)
        )
        await update.message.reply_text(f"🔇 User {uid} muted.")
        logging.info(f"User {uid} muted in {update.effective_chat.title}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

@active_group_only
async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not group_allowed(update.effective_chat.id):
        return await update.message.reply_text("🚫 Unauthorized group.")
    if not is_admin(update.effective_user.id):
        return await unauthorized(update, context)
    if not context.args:
        return await update.message.reply_text("Usage: /unmute <user_id>")

    uid = int(context.args[0])
    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id, uid,
            permissions=ChatPermissions(can_send_messages=True)
        )
        await update.message.reply_text(f"🔊 User {uid} unmuted.")
        logging.info(f"User {uid} unmuted in {update.effective_chat.title}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


# ====== LOCK / UNLOCK CHAT ======
@active_group_only
async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not group_allowed(update.effective_chat.id):
        return await update.message.reply_text("🚫 Unauthorized group.")
    if not is_admin(update.effective_user.id):
        return await unauthorized(update, context)

    LOCKED_CHATS.add(update.effective_chat.id)
    await update.message.reply_text("🔒 Chat locked. Only admins can send messages.")
    logging.info(f"Chat locked: {update.effective_chat.title}")

@active_group_only
async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not group_allowed(update.effective_chat.id):
        return await update.message.reply_text("🚫 Unauthorized group.")
    if not is_admin(update.effective_user.id):
        return await unauthorized(update, context)

    LOCKED_CHATS.discard(update.effective_chat.id)
    await update.message.reply_text("🔓 Chat unlocked!")
    logging.info(f"Chat unlocked: {update.effective_chat.title}")


# ====== BROADCAST ======
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await unauthorized(update, context)
    if not context.args:
        return await update.message.reply_text("Usage: /broadcast <text>")

    text = " ".join(context.args)
    sent, failed = 0, 0

    # Broadcast to private users
    for uid in list(USERS.keys()):
        try:
            await context.bot.send_message(int(uid), f"📢 *Broadcast:*\n{text}", parse_mode="Markdown")
            sent += 1
        except:
            failed += 1

    # Broadcast to groups
    for gid in ACTIVE_GROUPS:
        try:
            await context.bot.send_message(gid, f"📢 *Announcement:*\n{text}", parse_mode="Markdown")
            sent += 1
        except:
            failed += 1

    await update.message.reply_text(f"✅ Broadcast done.\n📨 Sent: {sent}\n❌ Failed: {failed}")
    logging.info(f"Broadcast sent by {update.effective_user.full_name}: {text}")

# ====== STATS / CLEANUP / RULES ======
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await unauthorized(update, context)
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    await update.message.reply_text(
        f"📊 *Bot Stats:*\n👥 Users: {len(USERS)}\n⚠️ Warnings: {len(WARNINGS)}\n"
        f"⏱ Uptime: {get_uptime()}\n🖥 CPU: {cpu}% | RAM: {ram}%",
        parse_mode="Markdown"
    )


async def listusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await unauthorized(update, context)
    text = "\n".join([f"{v['name']} (`{k}`)" for k, v in USERS.items()])
    await update.message.reply_text(f"👥 *Registered Users:*\n{text or 'No users.'}", parse_mode="Markdown")


async def cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USERS
    if not is_admin(update.effective_user.id):
        return await unauthorized(update, context)

    cutoff = time.time() - 7 * 24 * 3600
    before = len(USERS)
    USERS = {k: v for k, v in USERS.items() if v['last'] > cutoff}
    save_users()
    removed = before - len(USERS)
    await update.message.reply_text(f"🧹 Cleaned inactive users: {removed} removed.")

@active_group_only
async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📜 *Group Rules:*\n"
        "1️⃣ Be respectful\n"
        "2️⃣ No spam\n"
        "3️⃣ Stay on topic\n"
        "4️⃣ Use English only",
        parse_mode="Markdown"
    )


async def admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = await update.effective_chat.get_administrators()
    names = "\n".join([a.user.full_name for a in admins])
    await update.message.reply_text(f"👮 *Admins:*\n{names}", parse_mode="Markdown")


async def uptime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"⏱ *Bot Uptime:* {get_uptime()}", parse_mode="Markdown")


# ====== MESSAGE LOGGER ======
async def all_msgs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if chat.id in LOCKED_CHATS and not is_admin(user.id):
        try:
            await update.message.delete()
        except:
            pass
        return

    USERS[str(user.id)] = {"name": user.full_name, "last": time.time()}
    save_users()
# ======== MAIN ========

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    # User
    app.add_handler(CommandHandler("addgroup", addgroup))
    app.add_handler(CommandHandler("groups", groups))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("getmyid", get_my_id))
    app.add_handler(CommandHandler("userinfo", userinfo))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("feedback", feedback))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("uptime", uptime))
    app.add_handler(CommandHandler("getmyinfo", get_my_info))
    app.add_handler(CommandHandler("time", time_command))
    app.add_handler(CommandHandler("admins", admins))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("removegroup", removegroup))

    # Admin
    for cmd, func in {
    "ban": ban, "unban": unban, "mute": mute, "unmute": unmute,
        "lock": lock, "unlock": unlock, "broadcast": broadcast,
        "stats": stats, "listusers": listusers, "cleanup": cleanup,
        "groupinfo": groupinfo, "groups": groups,
        "addgroup": addgroup, "removegroup": removegroup
    }.items():
     app.add_handler(CommandHandler(cmd, func))

    # ✅ Welcome new members
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))

    # Log all messages


    app.add_handler(MessageHandler(filters.ALL, all_msgs))

    print("✅ Bot is running with advanced security & admin features...")
    app.run_polling()

if __name__ == "__main__":
    main()
