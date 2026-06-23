import discord
from discord.ext import commands
import wavelink
import asyncio
import aiosqlite
import time
import platform
import psutil
import json
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TOKEN")

async def get_prefix(bot, message):
    if not message.guild:
        return commands.when_mentioned_or("!")(bot, message)
    async with aiosqlite.connect("bot.db") as db:
        async with db.execute("SELECT prefix FROM guilds WHERE guild_id =?", (message.guild.id,)) as cursor:
            result = await cursor.fetchone()
            prefix = result[0] if result else "!"
    return commands.when_mentioned_or(prefix)(bot, message)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)
bot.start_time = time.time()

class Player(wavelink.Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.loop = False
        self.message = None
        self.ctx = None
        self.twenty_four_seven = False

NO_PREFIX_CMDS = ['play', 'p', 'skip', 's', 'stop', 'pause', 'resume', 'queue', 'q', 'np', 'loop', 'volume', 'vol', '247', 'ping', 'stats', 'help', 'saveplaylist', 'loadplaylist', 'myplaylists']

async def setup_db():
    async with aiosqlite.connect("bot.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS guilds (guild_id INTEGER PRIMARY KEY, prefix TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS playlists (user_id INTEGER, name TEXT, tracks TEXT, PRIMARY KEY (user_id, name))")
        await db.commit()

async def get_prefix_for_guild(guild_id):
    async with aiosqlite.connect("bot.db") as db:
        async with db.execute("SELECT prefix FROM guilds WHERE guild_id =?", (guild_id,)) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else "!"

class MusicButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.voice or not interaction.guild.voice_client:
            await interaction.response.send_message("Pehle VC me aa aur bot ko bulale", ephemeral=True)
            return False
        return True

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.blurple)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc: Player = interaction.guild.voice_client
        if vc.is_paused():
            await vc.resume()
            msg = "Resume ▶️"
        else:
            await vc.pause()
            msg = "Pause ⏸️"
        await interaction.response.send_message(msg, ephemeral=True)
        await update_now_playing(vc)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.blurple)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.guild.voice_client.stop()
        await interaction.response.send_message("Skip ⏭️", ephemeral=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.red)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc: Player = interaction.guild.voice_client
        vc.queue.clear()
        await vc.stop()
        await interaction.response.send_message("Stop ⏹️", ephemeral=True)
        await update_now_playing(vc)

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.grey)
    async def shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        interaction.guild.voice_client.queue.shuffle()
        await interaction.response.send_message("Queue shuffle 🔀", ephemeral=True)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.grey)
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc: Player = interaction.guild.voice_client
        vc.loop = not vc.loop
        await interaction.response.send_message(f"Loop **{'ON 🔁' if vc.loop else 'OFF'}**", ephemeral=True)
        await update_now_playing(vc)

class SearchSelect(discord.ui.Select):
    def __init__(self, ctx, tracks):
        self.ctx = ctx
        self.tracks = tracks
        options = [
            discord.SelectOption(
                label=f"{track.title[:80]}",
                description=f"{track.author[:50]} | {int(track.length//60000)}:{int(track.length%60000//1000):02d}",
                value=str(i)
            ) for i, track in enumerate(tracks[:5])
        ]
        super().__init__(placeholder="Gaana select karo...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user!= self.ctx.author:
            return await interaction.response.send_message("Ye menu tera nahi hai bhai", ephemeral=True)
        await interaction.response.defer()
        vc = await ensure_voice(self.ctx)
        if not vc: return
        track = self.tracks[int(self.values[0])]
        if vc.is_playing():
            await vc.queue.put_wait(track)
            await interaction.followup.send(f"Queue me add: **{track.title}**")
        else:
            await vc.play(track)
            embed = discord.Embed(title="Loading...", color=0x5865F2)
            vc.message = await interaction.followup.send(embed=embed, view=MusicButtons())
        await update_now_playing(vc)
        await interaction.message.delete()

class SearchView(discord.ui.View):
    def __init__(self, ctx, tracks):
        super().__init__(timeout=30)
        self.add_item(SearchSelect(ctx, tracks))

class HelpSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Music", description="Play, skip, search, queue", emoji="🎵"),
            discord.SelectOption(label="Playlist", description="Save/Load playlists", emoji="💾"),
            discord.SelectOption(label="Settings", description="Prefix, 24/7, loop", emoji="⚙️"),
            discord.SelectOption(label="Info", description="Ping, stats, bot info", emoji="📊"),
        ]
        super().__init__(placeholder="Category choose karo...", options=options)

    async def callback(self, interaction: discord.Interaction):
        prefix = await get_prefix_for_guild(interaction.guild.id)
        if self.values[0] == "Music":
            embed = discord.Embed(title="🎵 Music Commands", color=0x1DB954)
            embed.description = f"`{prefix}play <song/link>` - Gaana search + menu se select\n" \
                              f"`{prefix}skip` - Agla gaana\n" \
                              f"`{prefix}stop` - Gaana band + queue clear\n" \
                              f"`{prefix}pause` / `{prefix}resume` - Pause/Resume\n" \
                              f"`{prefix}queue` - Queue dekho\n" \
                              f"`{prefix}np` - Now playing\n" \
                              f"`{prefix}volume <0-200>` - Volume set karo\n" \
                              f"`{prefix}loop` - Ek gaana repeat\n\n" \
                              f"**No-Prefix:** `play`, `skip`, `queue` bina `{prefix}` ke chalega"
        elif self.values[0] == "Playlist":
            embed = discord.Embed(title="💾 Playlist Commands", color=0x9B59B6)
            embed.description = f"`{prefix}play <yt playlist>` - YouTube playlist load\n" \
                              f"`{prefix}saveplaylist <name>` - Current queue save karo\n" \
                              f"`{prefix}loadplaylist <name>` - Saved playlist bajao\n" \
                              f"`{prefix}myplaylists` - Teri saved playlists dekho"
        elif self.values[0] == "Settings":
            embed = discord.Embed(title="⚙️ Settings Commands", color=0x5865F2)
            embed.description = f"`{prefix}247` - 24/7 mode ON/OFF\n" \
                              f"`{prefix}prefix <new>` - Server prefix change karo\n" \
                              f"`{prefix}loop` - Loop ON/OFF toggle\n\n" \
                              f"**Note:** Prefix change karne ke liye `Manage Server` perm chahiye"
        elif self.values[0] == "Info":
            embed = discord.Embed(title="📊 Info Commands", color=0x00ff00)
            embed.description = f"`{prefix}ping` - Bot + Lavalink ping\n" \
                              f"`{prefix}stats` - Servers, uptime, CPU, RAM\n" \
                              f"`{prefix}help` - Ye menu kholo"
        await interaction.response.edit_message(embed=embed, view=HelpView())

class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(HelpSelect())

async def update_now_playing(vc: Player):
    if not vc or not vc.message:
        return
    if not vc.is_playing():
        embed = discord.Embed(title="Kuch Nahi Baj Raha", description="Gaana bajane ke liye `play <gaana/yt link/playlist>` likho", color=0x2b2d31)
        try:
            return await vc.message.edit(embed=embed, view=None)
        except:
            return
    track = vc.current
    position = vc.position
    length = track.length
    bar_pos = int(20 * position / length) if length else 0
    bar = "▬" * bar_pos + "🔘" + "▬" * (20 - bar_pos)
    embed = discord.Embed(title="Now Playing", description=f"**[{track.title}]({track.uri})**", color=0x1DB954)
    embed.add_field(name="Artist", value=track.author, inline=True)
    embed.add_field(name="Duration", value=f"{int(position//60000)}:{int(position%60000//1000):02d} / {int(length//60000)}:{int(length%60000//1000):02d}", inline=True)
    embed.add_field(name="Volume", value=f"{vc.volume}%", inline=True)
    embed.add_field(name="Loop", value="On 🔁" if vc.loop else "Off", inline=True)
    embed.add_field(name="Queue", value=f"{len(vc.queue)} songs", inline=True)
    embed.add_field(name="24/7", value="On" if vc.twenty_four_seven else "Off", inline=True)
    embed.add_field(name="", value=bar, inline=False)
    if track.artwork: embed.set_thumbnail(url=track.artwork)
    try:
        await vc.message.edit(embed=embed, view=MusicButtons())
    except:
        pass

async def ensure_voice(ctx):
    if not ctx.author.voice:
        await ctx.send("Pehle VC me aa bhai")
        return None
    if not ctx.voice_client:
        vc: Player = await ctx.author.voice.channel.connect(cls=Player)
        vc.ctx = ctx
    else:
        vc: Player = ctx.voice_client
    return vc

@bot.event
async def on_ready():
    await setup_db()
    print(f'{bot.user} GOD MODE ON 🔥')
    try:
        # WAVELINK V3 + TERA KHUD KA LAVALINK - FINAL FIX 🔥
        nodes = [
            wavelink.Node(
                identifier='Railway-Lavalink',
                uri='wss://my-lavalink-production-7115.up.railway.app',
                password='djbot123456'
            )
        ]
        await wavelink.Pool.connect(nodes=nodes, client=bot)
    except Exception as e:
        print(f"Lavalink Error: {e}")
    await bot.tree.sync()

@bot.event
async def on_wavelink_node_ready(payload: wavelink.NodeReadyEventPayload):
    print(f"Node {payload.node.identifier} ready!")

@bot.event
async def on_wavelink_track_start(payload: wavelink.TrackStartEventPayload):
    player = payload.player
    if not player: return
    await update_now_playing(player)

@bot.event
async def on_wavelink_track_end(payload: wavelink.TrackEndEventPayload):
    player = payload.player
    if not player: return
    if player.loop and payload.track:
        return await player.play(payload.track)
    if not player.queue.is_empty:
        next_track = await player.queue.get_wait()
        await player.play(next_track)
    elif not player.twenty_four_seven:
        await asyncio.sleep(120)
        if not player.is_playing() and len(player.channel.members) == 1:
            await player.disconnect()
    await update_now_playing(player)

@bot.event
async def on_message(message):
    if message.author.bot: return
    content = message.content.lower()
    split = content.split()
    if split and split[0] in NO_PREFIX_CMDS:
        message.content = (await get_prefix_for_guild(message.guild.id)) + message.content if message.guild else '!' + message.content
        await bot.process_commands(message)
        return
    await bot.process_commands(message)

@bot.command()
async def help(ctx):
    prefix = await get_prefix_for_guild(ctx.guild.id)
    embed = discord.Embed(title="👋 Help Menu", description=f"Dropdown se category select karo\n\n**Current Prefix:** `{prefix}`\n**No-Prefix:** Enabled\n**Features:** 24/7 + Search Menu + Saved Playlists", color=0x5865F2)
    embed.set_thumbnail(url=bot.user.avatar.url)
    await ctx.send(embed=embed, view=HelpView())

@bot.command()
@commands.has_permissions(manage_guild=True)
async def prefix(ctx, new_prefix: str = None):
    if new_prefix is None:
        current = await get_prefix_for_guild(ctx.guild.id)
        return await ctx.send(f"Current prefix: `{current}`\nChange: `prefix <new>`")
    if len(new_prefix) > 5:
        return await ctx.send("Prefix 5 characters se chota hona chahiye")
    async with aiosqlite.connect("bot.db") as db:
        await db.execute("INSERT OR REPLACE INTO guilds (guild_id, prefix) VALUES (?,?)", (ctx.guild.id, new_prefix))
        await db.commit()
    await ctx.send(f"✅ Prefix change: `{new_prefix}`")

@bot.command(aliases=['p'])
async def play(ctx, *, search: str = None):
    if not search: return await ctx.send("Gaana/Link to de bhai")
    vc = await ensure_voice(ctx)
    if not vc: return

    if "playlist?list=" in search or "&list=" in search:
        try:
            playlist = await wavelink.Playlist.search(search)
            if not playlist: return await ctx.send("YouTube playlist nahi mili 😢")
            for track in playlist.tracks:
                await vc.queue.put_wait(track)
            await ctx.send(f"YT Playlist **{playlist.name}** add: **{len(playlist.tracks)}** gaane 🔥")
            if not vc.is_playing():
                first_track = await vc.queue.get_wait()
                await vc.play(first_track)
                vc.message = await ctx.send("Loading...", view=MusicButtons())
            return await update_now_playing(vc)
        except:
            return await ctx.send("YouTube playlist load nahi hui")

    tracks = await wavelink.Playable.search(search)
    if not tracks: return await ctx.send("Gaana nahi mila 😢")
    if len(tracks) == 1:
        track = tracks[0]
        if vc.is_playing():
            await vc.queue.put_wait(track)
            await ctx.send(f"Queue me add: **{track.title}**")
        else:
            await vc.play(track)
            vc.message = await ctx.send("Loading...", view=MusicButtons())
        return await update_now_playing(vc)
    embed = discord.Embed(title="🔍 Search Results", description=f"`{search}` ke liye 5 results mile:", color=0x5865F2)
    await ctx.send(embed=embed, view=SearchView(ctx, tracks[:5]))

@bot.command(aliases=['247'])
async def twentyfour_seven(ctx):
    vc = await ensure_voice(ctx)
    if not vc: return
    vc.twenty_four_seven = not vc.twenty_four_seven
    await ctx.send(f"24/7 Mode **{'ON 🔁' if vc.twenty_four_seven else 'OFF'}**")
    await update_now_playing(vc)

@bot.command()
async def saveplaylist(ctx, *, name: str):
    vc: Player = ctx.voice_client
    if not vc or not vc.current:
        return await ctx.send("Kuch baj nahi raha, kya save karu?")
    tracks_data = [{"title": vc.current.title, "uri": vc.current.uri}]
    tracks_data.extend([{"title": t.title, "uri": t.uri} for t in list(vc.queue)])
    async with aiosqlite.connect("bot.db") as db:
        await db.execute("INSERT OR REPLACE INTO playlists (user_id, name, tracks) VALUES (?,?,?)", (ctx.author.id, name.lower(), json.dumps(tracks_data)))
        await db.commit()
    await ctx.send(f"✅ Playlist `{name}` save ho gayi with `{len(tracks_data)}` gaane\nLoad: `loadplaylist {name}`")

@bot.command()
async def loadplaylist(ctx, *, name: str):
    vc = await ensure_voice(ctx)
    if not vc: return
    async with aiosqlite.connect("bot.db") as db:
        async with db.execute("SELECT tracks FROM playlists WHERE user_id =? AND name =?", (ctx.author.id, name.lower())) as cursor:
            result = await cursor.fetchone()
    if not result:
        return await ctx.send(f"Playlist `{name}` nahi mili. `myplaylists` se check kar")
    tracks_data = json.loads(result[0])
    await ctx.send(f"Playlist `{name}` load ho rahi: `{len(tracks_data)}` gaane...")
    for track_info in tracks_data:
        tracks = await wavelink.Playable.search(track_info['uri'])
        if tracks: await vc.queue.put_wait(tracks[0])
    if not vc.is_playing():
        first_track = await vc.queue.get_wait()
        await vc.play(first_track)
        vc.message = await ctx.send("Loading...", view=MusicButtons())
    await update_now_playing(vc)

@bot.command()
async def myplaylists(ctx):
    async with aiosqlite.connect("bot.db") as db:
        async with db.execute("SELECT name FROM playlists WHERE user_id =?", (ctx.author.id,)) as cursor:
            results = await cursor.fetchall()
    if not results:
        return await ctx.send("Teri koi playlist saved nahi hai. `saveplaylist <name>` se save kar")
    pl_list = "\n".join([f"`{i+1}.` {row[0]}" for i, row in enumerate(results)])
    embed = discord.Embed(title="💾 Teri Saved Playlists", description=pl_list, color=0x9B59B6)
    embed.set_footer(text="Load karne ke liye: loadplaylist <name>")
    await ctx.send(embed=embed)

@bot.command(aliases=['s'])
async def skip(ctx):
    if ctx.voice_client: await ctx.voice_client.stop()

@bot.command()
async def stop(ctx):
    vc: Player = ctx.voice_client
    if vc:
        vc.queue.clear()
        await vc.stop()

@bot.command()
async def pause(ctx):
    vc: Player = ctx.voice_client
    if vc and vc.is_playing(): await vc.pause()

@bot.command()
async def resume(ctx):
    vc: Player = ctx.voice_client
    if vc and vc.is_paused(): await vc.resume()

@bot.command(aliases=['q'])
async def queue(ctx):
    vc: Player = ctx.voice_client
    if not vc or vc.queue.is_empty: return await ctx.send("Queue khali hai")
    queue_list = "\n".join([f"`{i+1}.` {t.title[:40]}" for i, t in enumerate(list(vc.queue)[:10])])
    embed = discord.Embed(title="Queue 📜", description=queue_list, color=0x5865F2)
    if len(vc.queue) > 10: embed.set_footer(text=f"...aur {len(vc.queue)-10} gaane")
    await ctx.send(embed=embed)

@bot.command()
async def loop(ctx):
    vc: Player = ctx.voice_client
    if vc:
        vc.loop = not vc.loop
        await ctx.send(f"Loop **{'ON 🔁' if vc.loop else 'OFF'}**")
        await update_now_playing(vc)

@bot.command(aliases=['vol'])
async def volume(ctx, vol: int):
    vc: Player = ctx.voice_client
    if vc and 0 <= vol <= 200:
        await vc.set_volume(vol)
        await ctx.send(f"Volume: **{vol}%** 🔊")
        await update_now_playing(vc)

@bot.command(aliases=['np'])
async def nowplaying(ctx):
    vc: Player = ctx.voice_client
    if vc: await update_now_playing(vc)

@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(title="🏓 Pong!", color=0x00ff00)
    embed.add_field(name="Bot Latency", value=f"`{latency}ms`", inline=True)
    if ctx.voice_client and ctx.voice_client.node:
        lavalink_ping = round(ctx.voice_client.node.heartbeat)
        embed.add_field(name="Lavalink Ping", value=f"`{lavalink_ping}ms`", inline=True)
    else:
        embed.add_field(name="Lavalink Ping", value="`Not Connected`", inline=True)
    await ctx.send(embed=embed)

@bot.command(aliases=['stats', 'botinfo'])
async def statistics(ctx):
    uptime_seconds = int(time.time() - bot.start_time)
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60
    uptime_str = f"{days}d {hours}h {minutes}m"
    vc_count = len([vc for vc in bot.voice_clients if vc.is_playing()])
    total_users = sum(guild.member_count for guild in bot.guilds)
    prefix = await get_prefix_for_guild(ctx.guild.id)
    embed = discord.Embed(title="📊 Bot Statistics", color=0x5865F2)
    embed.set_thumbnail(url=bot.user.avatar.url)
    embed.add_field(name="Prefix", value=f"`{prefix}`", inline=True)
    embed.add_field(name="Servers", value=f"`{len(bot.guilds)}`", inline=True)
    embed.add_field(name="Users", value=f"`{total_users}`", inline=True)
    embed.add_field(name="Playing In", value=f"`{vc_count}` VCs", inline=True)
    embed.add_field(name="Ping", value=f"`{round(bot.latency * 1000)}ms`", inline=True)
    embed.add_field(name="Uptime", value=f"`{uptime_str}`", inline=True)
    embed.add_field(name="CPU", value=f"`{psutil.cpu_percent()}%`", inline=True)
    embed.add_field(name="RAM", value=f"`{psutil.virtual_memory().percent}%`", inline=True)
    embed.add_field(name="discord.py", value=f"`{discord.__version__}`", inline=True)
    embed.set_footer(text=f"24/7 + No-Prefix Enabled")
    await ctx.send(embed=embed)

bot.run(TOKEN)
