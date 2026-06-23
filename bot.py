import discord
from discord.ext import commands
import wavelink
import asyncio
import os
import json

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

def get_prefix(bot, message):
    return commands.when_mentioned_or("!")(bot, message)

bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)

DATA_FILE = "data.json"
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'w') as f:
        json.dump({"playlists": {}, "247": {}}, f)

def load_data():
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

async def connect_nodes():
    await bot.wait_until_ready()
    node = wavelink.Node(
        identifier='Railway-Lavalink',
        uri='wss://my-lavalink-production-7115.up.railway.app:443',
        password='djbot123456'
    )
    await wavelink.Pool.connect(client=bot, nodes=[node])

@bot.event
async def on_ready():
    print(f'{bot.user} GOD MODE ON')
    await connect_nodes()

@bot.event
async def on_wavelink_node_ready(payload: wavelink.NodeReadyEventPayload):
    print(f'Node {payload.node.identifier} ready!')

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    no_prefix_cmds = ['play', 'p', 'skip', 's', 'stop', 'pause', 'resume', 'queue', 'q', 'nowplaying', 'np', 'volume', 'vol', 'shuffle', 'loop', '247', 'join', 'leave', 'dc', 'help', 'saveplaylist', 'loadplaylist', 'delplaylist']
    content = message.content.lower().split()
    if content and content[0] in no_prefix_cmds:
        message.content = "!" + message.content
        await bot.process_commands(message)
    else:
        await bot.process_commands(message)

class MusicControls(discord.ui.View):
    def __init__(self, vc):
        super().__init__(timeout=None)
        self.vc = vc

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.grey)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.vc:
            return await interaction.response.send_message("Bot VC me nahi hai", ephemeral=True)
        if self.vc.is_paused():
            await self.vc.resume()
            await interaction.response.send_message("Resumed", ephemeral=True)
        else:
            await self.vc.pause()
            await interaction.response.send_message("Paused", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.grey)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.vc or not self.vc.queue:
            return await interaction.response.send_message("Queue khali hai", ephemeral=True)
        await self.vc.skip()
        await interaction.response.send_message("Skipped", ephemeral=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.red)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.vc:
            return await interaction.response.send_message("Bot VC me nahi hai", ephemeral=True)
        self.vc.queue.clear()
        await self.vc.stop()
        await interaction.response.send_message("Stopped & Queue cleared", ephemeral=True)

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.blurple)
    async def shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.vc or len(self.vc.queue) < 2:
            return await interaction.response.send_message("Queue me 2+ songs chahiye", ephemeral=True)
        self.vc.queue.shuffle()
        await interaction.response.send_message("Queue shuffled", ephemeral=True)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.blurple)
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.vc:
            return await interaction.response.send_message("Bot VC me nahi hai", ephemeral=True)
        if self.vc.queue.loop:
            self.vc.queue.loop = False
            await interaction.response.send_message("Loop OFF", ephemeral=True)
        else:
            self.vc.queue.loop = True
            await interaction.response.send_message("Loop ON", ephemeral=True)

class SearchSelect(discord.ui.Select):
    def __init__(self, tracks, ctx):
        self.tracks = tracks
        self.ctx = ctx
        options = [
            discord.SelectOption(label=f"{i+1}. {track.title[:80]}", description=f"{track.author[:50]}", value=str(i))
            for i, track in enumerate(tracks[:5])
        ]
        super().__init__(placeholder="Gaana choose kar...", options=options)

    async def callback(self, interaction: discord.Interaction):
        track = self.tracks[int(self.values[0])]
        vc: wavelink.Player = self.ctx.voice_client
        if not vc:
            vc = await self.ctx.author.voice.channel.connect(cls=wavelink.Player)
        await vc.play(track)
        embed = discord.Embed(title="Ab Baj Raha Hai", description=f"**{track.title}**\nBy: {track.author}", color=0x00ff00)
        await interaction.response.edit_message(content=None, embed=embed, view=MusicControls(vc))

class SearchView(discord.ui.View):
    def __init__(self, tracks, ctx):
        super().__init__(timeout=60)
        self.add_item(SearchSelect(tracks, ctx))

@bot.command(aliases=['p'])
async def play(ctx, *, query: str):
    if not ctx.author.voice:
        return await ctx.send("Pehle VC join kar le bhai")
    vc: wavelink.Player = ctx.voice_client
    if not vc:
        vc = await ctx.author.voice.channel.connect(cls=wavelink.Player)
    if "youtube.com/playlist" in query or "list=" in query:
        await ctx.send("Playlist load kar raha hu...")
        playlist = await wavelink.Playable.search(query)
        if not playlist:
            return await ctx.send("Playlist nahi mili")
        for track in playlist:
            vc.queue.put(track)
        if not vc.playing:
            await vc.play(vc.queue.get())
        return await ctx.send(f"Playlist loaded! {len(playlist)} songs queue me add kar diye")
    tracks = await wavelink.Playable.search(query)
    if not tracks:
        return await ctx.send("Gaana nahi mila")
    if len(tracks) == 1 or query.startswith("http"):
        track = tracks[0]
        if vc.playing:
            vc.queue.put(track)
            return await ctx.send(f"Queue me add kiya: **{track.title}**")
        await vc.play(track)
        embed = discord.Embed(title="Ab Baj Raha Hai", description=f"**{track.title}**\nBy: {track.author}", color=0x00ff00)
        await ctx.send(embed=embed, view=MusicControls(vc))
    else:
        embed = discord.Embed(title="Search Results", description=f"**{query}** ke liye 5 results mile:", color=0x00ffff)
        await ctx.send(embed=embed, view=SearchView(tracks[:5], ctx))

@bot.command(aliases=['s'])
async def skip(ctx):
    vc: wavelink.Player = ctx.voice_client
    if not vc or not vc.playing:
        return await ctx.send("Kuch baj nahi raha")
    await vc.skip()
    await ctx.send("Skipped")

@bot.command()
async def stop(ctx):
    vc: wavelink.Player = ctx.voice_client
    if not vc:
        return await ctx.send("Bot VC me nahi hai")
    vc.queue.clear()
    await vc.stop()
    await ctx.send("Stopped & Queue cleared")

@bot.command()
async def pause(ctx):
    vc: wavelink.Player = ctx.voice_client
    if not vc or not vc.playing:
        return await ctx.send("Kuch baj nahi raha")
    await vc.pause()
    await ctx.send("Paused")

@bot.command()
async def resume(ctx):
    vc: wavelink.Player = ctx.voice_client
    if not vc or not vc.is_paused():
        return await ctx.send("Paused nahi hai")
    await vc.resume()
    await ctx.send("Resumed")

@bot.command(aliases=['q'])
async def queue(ctx):
    vc: wavelink.Player = ctx.voice_client
    if not vc or not vc.queue:
        return await ctx.send("Queue khali hai")
    queue_list = "\n".join([f"`{i+1}.` {track.title[:50]}" for i, track in enumerate(list(vc.queue)[:10])])
    embed = discord.Embed(title="Queue", description=queue_list, color=0x00ffff)
    embed.set_footer(text=f"Total: {len(vc.queue)} songs")
    await ctx.send(embed=embed)

@bot.command(aliases=['np'])
async def nowplaying(ctx):
    vc: wavelink.Player = ctx.voice_client
    if not vc or not vc.current:
        return await ctx.send("Kuch baj nahi raha")
    track = vc.current
    embed = discord.Embed(title="Ab Baj Raha Hai", description=f"**{track.title}**\nBy: {track.author}", color=0x00ff00)
    await ctx.send(embed=embed)

@bot.command(aliases=['vol'])
async def volume(ctx, vol: int):
    vc: wavelink.Player = ctx.voice_client
    if not vc:
        return await ctx.send("Bot VC me nahi hai")
    if not 0 <= vol <= 100:
        return await ctx.send("Volume 0-100 ke beech rakho")
    await vc.set_volume(vol)
    await ctx.send(f"Volume set to {vol}%")

@bot.command()
async def shuffle(ctx):
    vc: wavelink.Player = ctx.voice_client
    if not vc or len(vc.queue) < 2:
        return await ctx.send("Queue me 2+ songs chahiye")
    vc.queue.shuffle()
    await ctx.send("Queue shuffled")

@bot.command()
async def loop(ctx):
    vc: wavelink.Player = ctx.voice_client
    if not vc:
        return await ctx.send("Bot VC me nahi hai")
    if vc.queue.loop:
        vc.queue.loop = False
        await ctx.send("Loop OFF")
    else:
        vc.queue.loop = True
        await ctx.send("Loop ON")

@bot.command()
async def join(ctx):
    if not ctx.author.voice:
        return await ctx.send("Pehle VC join kar")
    await ctx.author.voice.channel.connect(cls=wavelink.Player)
    await ctx.send("VC join kar liya")

@bot.command(aliases=['dc', 'leave'])
async def disconnect(ctx):
    vc: wavelink.Player = ctx.voice_client
    if not vc:
        return await ctx.send("Bot VC me nahi hai")
    await vc.disconnect()
    await ctx.send("VC se nikal gaya")

@bot.command(name="247")
async def _247(ctx):
    data = load_data()
    guild_id = str(ctx.guild.id)
    if guild_id in data["247"]:
        del data["247"][guild_id]
        await ctx.send("24/7 Mode OFF")
    else:
        if not ctx.author.voice:
            return await ctx.send("Pehle VC join kar")
        data["247"][guild_id] = ctx.author.voice.channel.id
        await ctx.send("24/7 Mode ON - Bot VC me hi rahega")
    save_data(data)

@bot.command()
async def saveplaylist(ctx, name: str):
    vc: wavelink.Player = ctx.voice_client
    if not vc or not vc.queue:
        return await ctx.send("Queue khali hai")
    data = load_data()
    user_id = str(ctx.author.id)
    if user_id not in data["playlists"]:
        data["playlists"][user_id] = {}
    tracks = [{"title": t.title, "uri": t.uri} for t in list(vc.queue)]
    data["playlists"][user_id][name] = tracks
    save_data(data)
    await ctx.send(f"Playlist {name} save ho gayi with {len(tracks)} songs")

@bot.command()
async def loadplaylist(ctx, name: str):
    data = load_data()
    user_id = str(ctx.author.id)
    if user_id not in data["playlists"] or name not in data["playlists"][user_id]:
        return await ctx.send("Playlist nahi mili")
    if not ctx.author.voice:
        return await ctx.send("Pehle VC join kar")
    vc: wavelink.Player = ctx.voice_client
    if not vc:
        vc = await ctx.author.voice.channel.connect(cls=wavelink.Player)
    tracks = data["playlists"][user_id][name]
    for track_data in tracks:
        track = await wavelink.Playable.search(track_data["uri"])
        if track:
            vc.queue.put(track[0])
    if not vc.playing:
        await vc.play(vc.queue.get())
    await ctx.send(f"Playlist {name} loaded! {len(tracks)} songs queue me")

@bot.command()
async def delplaylist(ctx, name: str):
    data = load_data()
    user_id = str(ctx.author.id)
    if user_id not in data["playlists"] or name not in data["playlists"][user_id]:
        return await ctx.send("Playlist nahi mili")
    del data["playlists"][user_id][name]
    save_data(data)
    await ctx.send(f"Playlist {name} delete kar di")

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="ALIBUUU DJ BOT", description="Hydra Jaisa Pro DJ Bot\nNo prefix needed! Direct command likho", color=0x00ffff)
    if bot.user.avatar:
        embed.set_thumbnail(url=bot.user.avatar.url)
    embed.add_field(name="Music", value="`play`, `skip`, `stop`, `pause`, `resume`, `queue`, `np`, `volume`, `shuffle`, `loop`", inline=False)
    embed.add_field(name="VC", value="`join`, `leave`, `247`", inline=False)
    embed.add_field(name="Playlist", value="`saveplaylist <name>`, `loadplaylist <name>`, `delplaylist <name>`", inline=False)
    embed.add_field(name="Features", value="No prefix commands\nYT Playlist support\nSearch menu with 5 options\n24/7 VC mode\nCustom playlists\nButton controls", inline=False)
    embed.set_footer(text="Developed by KALESSSSSXXX | Type help for commands")
    class HelpSelect(discord.ui.Select):
        def __init__(self):
            options = [
                discord.SelectOption(label="Music Commands", description="play, skip, queue etc", emoji="🎵"),
                discord.SelectOption(label="VC Commands", description="join, 24/7 etc", emoji="🔊"),
                discord.SelectOption(label="Playlist Commands", description="save/load playlists", emoji="💾")
            ]
            super().__init__(placeholder="Category choose kar...", options=options)
        async def callback(self, interaction: discord.Interaction):
            if self.values[0] == "Music Commands":
                await interaction.response.send_message("**Music Commands:**\n`play <song>` - Gaana bajao\n`skip` - Next song\n`stop` - Roko aur queue clear\n`pause/resume` - Pause/Resume\n`queue` - Queue dekho\n`nowplaying` - Ab kya baj raha\n`volume 0-100` - Volume set\n`shuffle` - Queue shuffle\n`loop` - Loop on/off", ephemeral=True)
            elif self.values[0] == "VC Commands":
                await interaction.response.send_message("**VC Commands:**\n`join` - VC join karo\n`leave` - VC se niklo\n`247` - 24/7 mode on/off", ephemeral=True)
            elif self.values[0] == "Playlist Commands":
                await interaction.response.send_message("**Playlist Commands:**\n`saveplaylist <name>` - Current queue save\n`loadplaylist <name>` - Playlist load\n`delplaylist <name>` - Playlist delete", ephemeral=True)
    class HelpView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)
            self.add_item(HelpSelect())
    await ctx.send(embed=embed, view=HelpView())

@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id and before.channel and not after.channel:
        data = load_data()
        guild_id = str(member.guild.id)
        if guild_id in data["247"]:
            channel = bot.get_channel(data["247"][guild_id])
            if channel:
                await asyncio.sleep(1)
                await channel.connect(cls=wavelink.Player)

bot.run(os.getenv('DISCORD_TOKEN'))
