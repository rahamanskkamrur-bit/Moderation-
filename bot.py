import asyncio, datetime, os, re, time, aiohttp
from aiohttp import web
import discord
from discord.ext import commands

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
STAFF_ROLE_IDS = [1567026563369664590]
MOD_LOG_CHANNEL_ID = 1567026568423931975
START_TIME = time.time()
BOT_STATUS = "Starting..."

BAD_WORDS = ["discord.gg/", "discord.com/invite/", "free nitro", "steamcommunnity", "dox", "ddos", "token grab", "nuke"]

async def handle_ping(req):
    up = int((time.time() - START_TIME) // 60)
    return web.Response(text=f"Moderator Bot 24/7 | Uptime: {up}m | Status: {BOT_STATUS}")

async def run_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    await web.TCPSite(runner, "0.0.0.0", port).start()

async def self_ping_loop():
    await asyncio.sleep(20)
    url = os.environ.get("RENDER_EXTERNAL_URL") or f"http://127.0.0.1:{os.environ.get('PORT', 10000)}/"
    async with aiohttp.ClientSession() as s:
        while True:
            try:
                async with s.get(url, timeout=10): pass
            except Exception: pass
            await asyncio.sleep(240)

def is_mod(m: discord.Member) -> bool:
    if not isinstance(m, discord.Member): return False
    return m.guild_permissions.administrator or m.guild_permissions.moderate_members or any(r.id in STAFF_ROLE_IDS for r in m.roles)

async def send_mod_log(guild: discord.Guild, embed: discord.Embed, view: discord.ui.View = None):
    log_ch = guild.get_channel(MOD_LOG_CHANNEL_ID)
    if log_ch:
        try:
            await log_ch.send(embed=embed, view=view)
        except Exception:
            pass

class ModLogActionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def get_target_id(self, emb: discord.Embed):
        m = re.search(r"ID:\s*`(\d+)`", emb.description or "")
        return int(m.group(1)) if m else None

    @discord.ui.button(label="Remove Timeout", style=discord.ButtonStyle.success, emoji="🔓", custom_id="modlog:unmute")
    async def unmute_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_mod(interaction.user):
            return await interaction.response.send_message("❌ Moderators only.", ephemeral=True)
        tid = self.get_target_id(interaction.message.embeds[0])
        member = interaction.guild.get_member(tid) if tid else None
        if member:
            await member.timeout(None, reason=f"Timeout removed by {interaction.user}")
            await interaction.response.send_message(f"🔓 {interaction.user.mention} removed the timeout for {member.mention}.")
        else:
            await interaction.response.send_message("⚠️ Member not found in server.", ephemeral=True)

    @discord.ui.button(label="Ban Offender", style=discord.ButtonStyle.danger, emoji="🔨", custom_id="modlog:ban")
    async def ban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_mod(interaction.user):
            return await interaction.response.send_message("❌ Moderators only.", ephemeral=True)
        tid = self.get_target_id(interaction.message.embeds[0])
        if tid:
            await interaction.guild.ban(discord.Object(id=tid), reason=f"Banned via Mod-Log by {interaction.user}")
            await interaction.response.send_message(f"🔨 {interaction.user.mention} banned User ID `{tid}`.")

class ModeratorBot(commands.Bot):
    def __init__(self, msg_intent: bool = True):
        intents = discord.Intents.default()
        intents.message_content = msg_intent
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(ModLogActionView())
        await self.tree.sync()

    async def on_ready(self):
        global BOT_STATUS
        BOT_STATUS = f"ONLINE as {self.user}"
        print(f"✅ Moderator Bot ONLINE as {self.user}")

    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        await self.process_commands(message)

        if is_mod(message.author):
            return

        low = message.content.lower()
        triggered = next((w for w in BAD_WORDS if w in low), None)
        if not triggered and len(message.mentions) >= 5:
            triggered = "Mass Mention Spam (5+ pings)"

        if triggered:
            try:
                await message.delete()
            except Exception:
                pass
            until = discord.utils.utcnow() + datetime.timedelta(minutes=10)
            timed_out = False
            try:
                await message.author.timeout(until, reason=f"Auto-Mod: {triggered}")
                timed_out = True
            except Exception:
                pass

            warn_emb = discord.Embed(
                title="🛡️ Auto-Moderator Action",
                description=f"{message.author.mention}, your message was removed for triggering **`{triggered}`**." + ("\n⏱️ **10-minute timeout applied.**" if timed_out else ""),
                color=discord.Color.red(),
            )
            await message.channel.send(embed=warn_emb, delete_after=10)

            log_emb = discord.Embed(
                title="🚨 Auto-Mod Violation Logged",
                description=f"👤 **Offender:** {message.author.mention} (ID: `{message.author.id}`)\n📍 **Channel:** {message.channel.mention}\n⚠️ **Trigger:** `{triggered}`\n💬 **Message:** `{message.content[:300]}`",
                color=discord.Color.dark_red(),
            )
            await send_mod_log(message.guild, log_emb, ModLogActionView())

def reg_cmds(b: ModeratorBot):
    @b.tree.command(name="warn", description="Warn a member and log the warning")
    async def warn_cmd(interaction: discord.Interaction, member: discord.Member, reason: str):
        if not is_mod(interaction.user):
            return await interaction.response.send_message("❌ Moderators only.", ephemeral=True)
        emb = discord.Embed(
            title="⚠️ Official Server Warning",
            description=f"👤 **Member:** {member.mention} (ID: `{member.id}`)\n🛡️ **Moderator:** {interaction.user.mention}\n📌 **Reason:** {reason}",
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(content=member.mention, embed=emb)
        await send_mod_log(interaction.guild, emb)

    @b.tree.command(name="timeout", description="Timeout a member for a set number of minutes")
    async def timeout_cmd(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "Rule violation"):
        if not is_mod(interaction.user):
            return await interaction.response.send_message("❌ Moderators only.", ephemeral=True)
        until = discord.utils.utcnow() + datetime.timedelta(minutes=max(1, min(minutes, 40320)))
        await member.timeout(until, reason=f"{reason} (by {interaction.user})")
        emb = discord.Embed(
            title="🔇 Member Timed Out",
            description=f"👤 **Member:** {member.mention} (ID: `{member.id}`)\n⏱️ **Duration:** `{minutes} minutes`\n🛡️ **Moderator:** {interaction.user.mention}\n📌 **Reason:** {reason}",
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=emb)
        await send_mod_log(interaction.guild, emb, ModLogActionView())

    @b.tree.command(name="untimeout", description="Remove an active timeout from a member")
    async def untimeout_cmd(interaction: discord.Interaction, member: discord.Member):
        if not is_mod(interaction.user):
            return await interaction.response.send_message("❌ Moderators only.", ephemeral=True)
        await member.timeout(None, reason=f"Removed by {interaction.user}")
        emb = discord.Embed(
            title="🔓 Timeout Removed",
            description=f"👤 **Member:** {member.mention} (ID: `{member.id}`)\n🛡️ **Moderator:** {interaction.user.mention}",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=emb)
        await send_mod_log(interaction.guild, emb)

    @b.tree.command(name="purge", description="Delete a number of recent messages in this channel")
    async def purge_cmd(interaction: discord.Interaction, amount: int):
        if not is_mod(interaction.user):
            return await interaction.response.send_message("❌ Moderators only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=max(1, min(amount, 100)))
        emb = discord.Embed(
            title="🧹 Channel Purged",
            description=f"📍 **Channel:** {interaction.channel.mention}\n🗑️ **Messages Deleted:** `{len(deleted)}`\n🛡️ **Moderator:** {interaction.user.mention}",
            color=discord.Color.blurple(),
        )
        await send_mod_log(interaction.guild, emb)
        await interaction.followup.send(f"🧹 Deleted **{len(deleted)}** messages!", ephemeral=True)

    @b.tree.command(name="kick", description="Kick a member from the server")
    async def kick_cmd(interaction: discord.Interaction, member: discord.Member, reason: str = "Rule violation"):
        if not is_mod(interaction.user):
            return await interaction.response.send_message("❌ Moderators only.", ephemeral=True)
        await member.kick(reason=f"{reason} (by {interaction.user})")
        emb = discord.Embed(
            title="👢 Member Kicked",
            description=f"👤 **Member:** {member} (ID: `{member.id}`)\n🛡️ **Moderator:** {interaction.user.mention}\n📌 **Reason:** {reason}",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=emb)
        await send_mod_log(interaction.guild, emb)

    @b.tree.command(name="ban", description="Ban a member from the server")
    async def ban_cmd(interaction: discord.Interaction, member: discord.Member, reason: str = "Rule violation"):
        if not is_mod(interaction.user):
            return await interaction.response.send_message("❌ Moderators only.", ephemeral=True)
        await member.ban(reason=f"{reason} (by {interaction.user})")
        emb = discord.Embed(
            title="🔨 Member Banned",
            description=f"👤 **Member:** {member} (ID: `{member.id}`)\n🛡️ **Moderator:** {interaction.user.mention}\n📌 **Reason:** {reason}",
            color=discord.Color.dark_red(),
        )
        await interaction.response.send_message(embed=emb)
        await send_mod_log(interaction.guild, emb)

async def main():
    await run_web_server()
    asyncio.create_task(self_ping_loop())
    if not BOT_TOKEN:
        while True: await asyncio.sleep(3600)
    bot = ModeratorBot(True)
    reg_cmds(bot)
    try:
        await bot.start(BOT_TOKEN)
    except discord.PrivilegedIntentsRequired:
        await bot.close()
        bot = ModeratorBot(False)
        reg_cmds(bot)
        await bot.start(BOT_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
  
