import discord
import wavelink
import os
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

class MusicBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.song_queues = {}
        bot.loop.create_task(self.connect_nodes())

    async def connect_nodes(self):
        await self.bot.wait_until_ready()

        # 3 LAVALINK NODES - EK DOWN HO TO DUSRA CHALEGA
        nodes = [
            wavelink.Node(
                uri=os.getenv("LAVALINK_URI"),
                password=os.getenv("LAVALINK_PASSWORD")
            ),
            wavelink.Node(
                uri="wss://lava-v4.ajieblogs.eu.org:443",
                password="https://dsc.gg/ajidevserver"
            ),
            wavelink.Node(
                uri="wss://lavalink.alfari.id:443",
                password="https://dsc.gg/ajidevserver"
            )
        ]

        await wavelink.Pool.connect(client=bot, nodes=nodes)

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        print(f"Node {payload.node.identifier} ready!")

    @commands.command()
    async def play(self, ctx, *, search: str):
        if not ctx.author.voice:
            return await ctx.send("Join a voice channel first")

        vc: wavelink.Player = ctx.voice_client
        if not vc:
            vc = await ctx.author.voice.channel.connect(cls=wavelink.Player)

        tracks = await wavelink.Playable.search(search)
        if not tracks:
            return await ctx.send("No results found")

        track = tracks[0]
        if vc.playing:
            if ctx.guild.id not in self.song_queues:
                self.song_queues[ctx.guild.id] = []
            self.song_queues[ctx.guild.id].append(track)
            await ctx.send(f"Added to queue: **{track.title}**")
        else:
            await vc.play(track)
            await ctx.send(f"Now playing: **{track.title}**")

    @commands.command()
    async def skip(self, ctx):
        vc: wavelink.Player = ctx.voice_client
        if vc:
            await vc.skip()
            await ctx.send("Skipped")

    @commands.command()
    async def stop(self, ctx):
        vc: wavelink.Player = ctx.voice_client
        if vc:
            self.song_queues[ctx.guild.id] = []
            await vc.stop()
            await ctx.send("Stopped and cleared queue")

    @commands.command()
    async def pause(self, ctx):
        vc: wavelink.Player = ctx.voice_client
        if vc:
            await vc.pause(True)
            await ctx.send("Paused")

    @commands.command()
    async def resume(self, ctx):
        vc: wavelink.Player = ctx.voice_client
        if vc:
            await vc.pause(False)
            await ctx.send("Resumed")

    @commands.command()
    async def queue(self, ctx):
        if ctx.guild.id not in self.song_queues or not self.song_queues[ctx.guild.id]:
            return await ctx.send("Queue is empty")

        queue_list = "\n".join([f"{i+1}. {track.title}" for i, track in enumerate(self.song_queues[ctx.guild.id][:10])])
        await ctx.send(f"**Queue:**\n{queue_list}")

    @commands.command()
    async def volume(self, ctx, vol: int):
        vc: wavelink.Player = ctx.voice_client
        if vc:
            await vc.set_volume(vol)
            await ctx.send(f"Volume set to {vol}%")

    @commands.command()
    async def join(self, ctx):
        if not ctx.author.voice:
            return await ctx.send("Join a voice channel first")
        await ctx.author.voice.channel.connect(cls=wavelink.Player)
        await ctx.send("Joined your VC")

    @commands.command()
    async def leave(self, ctx):
        vc: wavelink.Player = ctx.voice_client
        if vc:
            await vc.disconnect()
            await ctx.send("Left VC")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        if payload.player.guild.id in self.song_queues and self.song_queues[payload.player.guild.id]:
            next_track = self.song_queues[payload.player.guild.id].pop(0)
            await payload.player.play(next_track)

async def setup(bot):
    await bot.add_cog(MusicBot(bot))
