import discord
from discord.ext import commands
import wavelink
import os
import asyncio

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

class MusicControls(discord.ui.View):
    def __init__(self, vc):
        super().__init__(timeout=None)
        self.vc = vc

    @discord.ui.button(emoji="⏯", style=discord.ButtonStyle.grey)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.vc:
            return await interaction.response.send_message("Bot VC me nahi hai", ephemeral=True)
        if self.vc.is_paused():
            await self.vc.resume()
            await interaction.response.send_message("Resumed", ephemeral=True)
        else:
            await self.vc.pause()
            await interaction.response.send_message("Paused", ephemeral=True)

    @discord.ui.button(emoji="⏭", style=discord.ButtonStyle.grey)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.vc or not self.vc.queue:
            return await interaction.response.send_message("Queue khali hai", ephemeral=True)
        await self.vc.skip()
        await interaction.response.send_message("Skipped", ephemeral=True)

    @discord.ui.button(emoji="⏹", style=discord.ButtonStyle.red)
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
        self.vc.queue.loop = not self.vc.queue.loop
        status = "ON" if self.vc.queue.loop else "OFF"
        await interaction.response.send_message(f"Loop {status}", ephemeral=True)

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
    if message.author.bot or not message.guild:
        return

    content = message.content.lower().strip()
    args = content.split()
    if not args:
        return

    cmd = args[0]
    query = " ".join(args[1:]) if len(args) > 1 else ""
    vc: wavelink.Player = message.guild.voice_client

    # HELP
    if cmd == "help":
        embed = discord.Embed(title="ALIBUUU Music Bot", description="Sab commands no-prefix hai", color=0x2b2d31)
        embed.add_field(name="Music", value="`play <song>` `skip` `pause` `resume` `stop`\n`queue` `nowplaying` `volume <1-100>`", inline=False)
        embed.add_field(name="DJ", value="`seek <sec>` `shuffle` `loop` `247`", inline=False)
        embed.add_field(name="VC", value="`join` `leave` `ping`", inline=False)
        embed.set_footer(text="Example: play kesariya")
        await message.channel.send(embed=embed)

    # JOIN
    elif cmd == "join":
        if not message.author.voice:
            return await message.channel.send("Pehle VC join kar le bhai")
        if not vc:
            await message.author.voice.channel.connect(cls=wavelink.Player)
            await message.channel.send("Aa gaya VC me")
        else:
            await message.channel.send("Pehle se VC me hu")

    # LEAVE
    elif cmd == "leave":
        if vc:
            await vc.disconnect()
            await message.channel.send("Chala gaya VC se")
        else:
            await message.channel.send("VC me hu hi nahi")

    # PLAY
    elif cmd in ["play", "p"]:
        if not query:
            return await message.channel.send("Gaane ka naam to de: `play kesariya`")
        if not message.author.voice:
            return await message.channel.send("Pehle VC join kar le")
        if not vc:
            vc = await message.author.voice.channel.connect(cls=wavelink.Player)

        tracks = await wavelink.Playable.search(query)
        if not tracks:
            return await message.channel.send("Kuch nahi mila")

        embed = discord.Embed(color=0x2b2d31)
        if isinstance(tracks, wavelink.Playlist):
            for track in tracks.tracks:
                await vc.queue.put_wait(track)
            embed.description = f"Playlist Add: **{tracks.name}**\n{len(tracks.tracks)} songs queued"
        else:
            track = tracks[0]
            await vc.queue.put_wait(track)
            embed.description = f"Queued: **{track.title}**"
            embed.set_thumbnail(url=track.artwork)

        if not vc.playing:
            await vc.play(vc.queue.get())

        await message.channel.send(embed=embed, view=MusicControls(vc))

    # SKIP
    elif cmd in ["skip", "s"]:
        if vc and vc.playing:
            await vc.skip()
            await message.channel.send("Skipped ⏭")
        else:
            await message.channel.send("Kuch baj hi nahi raha")

    # PAUSE
    elif cmd == "pause":
        if vc and vc.playing:
            await vc.pause()
            await message.channel.send("Paused ⏸")
        else:
            await message.channel.send("Baj hi nahi raha to pause kya karu")

    # RESUME
    elif cmd == "resume":
        if vc and vc.is_paused():
            await vc.resume()
            await message.channel.send("Resumed ▶")
        else:
            await message.channel.send("Paused hi nahi hai")

    # STOP
    elif cmd == "stop":
        if vc:
            vc.queue.clear()
            await vc.stop()
            await message.channel.send("Stopped & Queue cleared ⏹")
        else:
            await message.channel.send("VC me hu hi nahi")

    # QUEUE
    elif cmd in ["queue", "q"]:
        if not vc or not vc.queue:
            return await message.channel.send("Queue khali hai")
        queue_list = "\n".join([f"`{i+1}.` {track.title[:40]}" for i, track in enumerate(vc.queue[:10])])
        embed = discord.Embed(title="Queue", description=queue_list, color=0x2b2d31)
        embed.set_footer(text=f"Total: {len(vc.queue)} songs")
        await message.channel.send(embed=embed)

    # NOWPLAYING
    elif cmd in ["nowplaying", "np"]:
        if vc and vc.current:
            embed = discord.Embed(title="Now Playing", description=f"**{vc.current.title}**", color=0x2b2d31)
            embed.set_thumbnail(url=vc.current.artwork)
            pos = int(vc.position / 1000)
            dur = int(vc.current.length / 1000)
            embed.add_field(name="Progress", value=f"{pos//60}:{pos%60:02d} / {dur//60}:{dur%60:02d}")
            await message.channel.send(embed=embed, view=MusicControls(vc))
        else:
            await message.channel.send("Kuch baj hi nahi raha")

    # VOLUME
    elif cmd == "volume":
        if not vc:
            return await message.channel.send("VC me nahi hu")
        if not query or not query.isdigit():
            return await message.channel.send(f"Current volume: `{vc.volume}%`\nSet karne ke liye: `volume 50`")
        vol = int(query)
        if 0 <= vol <= 100:
            await vc.set_volume(vol)
            await message.channel.send(f"Volume set: `{vol}%`")
        else:
            await message.channel.send("Volume 0-100 ke beech rakh")

    # SEEK
    elif cmd == "seek":
        if not vc or not vc.playing:
            return await message.channel.send("Kuch baj hi nahi raha")
        if not query or not query.isdigit():
            return await message.channel.send("Time de seconds me: `seek 60`")
        await vc.seek(int(query) * 1000)
        await message.channel.send(f"Seek: `{query}s`")

    # SHUFFLE
    elif cmd == "shuffle":
        if not vc or len(vc.queue) < 2:
            return await message.channel.send("Queue me 2+ songs chahiye")
        vc.queue.shuffle()
        await message.channel.send("Queue shuffled 🔀")

    # LOOP
    elif cmd == "loop":
        if not vc:
            return await message.channel.send("VC me nahi hu")
        vc.queue.loop = not vc.queue.loop
        status = "ON" if vc.queue.loop else "OFF"
        await message.channel.send(f"Loop {status} 🔁")

    # 247
    elif cmd == "247":
        if not vc:
            if not message.author.voice:
                return await message.channel.send("Pehle VC join kar")
            vc = await message.author.voice.channel.connect(cls=wavelink.Player)
        vc.autoplay = wavelink.AutoPlayMode.enabled
        await message.channel.send("24/7 Mode ON 🔥 Autoplay chalu")

    # PING
    elif cmd == "ping":
        await message.channel.send(f"Pong! `{round(bot.latency * 1000)}ms`")

bot.run(os.getenv('DISCORD_TOKEN'))
