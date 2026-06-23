import discord
from discord.ext import commands
import wavelink
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

async def connect_nodes():
    await bot.wait_until_ready()
    
    # TEEN LAVALINK NODES - EK DOWN HO TO DUSRA CHALEGA
    nodes = [
        wavelink.Node(
            identifier='Node-1-Main',
            uri='wss://lava-v4.ajieblogs.eu.org:443',
            password='https://dsc.gg/ajidevserver'
        ),
        wavelink.Node(
            identifier='Node-2-Backup',
            uri='wss://lavalink.alfari.id:443',
            password='https://dsc.gg/ajidevserver'
        ),
        wavelink.Node(
            identifier='Node-3-Extra',
            uri='wss://lavalink.jirayu.net:443',
            password='youshallnotpass'
        )
    ]
    
    await wavelink.Pool.connect(client=bot, nodes=nodes)

@bot.event
async def on_ready():
    print(f'{bot.user} login ho gaya!')
    bot.loop.create_task(connect_nodes())

@bot.event
async def on_wavelink_node_ready(payload: wavelink.NodeReadyEventPayload):
    print(f'Node {payload.node.identifier} ready!')

@bot.event
async def on_wavelink_node_disconnected(payload: wavelink.NodeDisconnectedEventPayload):
    print(f'Node {payload.node.identifier} disconnected, auto failover hoga')

@bot.command()
async def join(ctx):
    if not ctx.author.voice:
        return await ctx.send("Pehle VC join kar bhai")
    await ctx.author.voice.channel.connect(cls=wavelink.Player)
    await ctx.send("VC me aa gaya 🎵")

@bot.command()
async def play(ctx, *, search: str):
    vc: wavelink.Player = ctx.voice_client
    if not vc:
        vc = await ctx.author.voice.channel.connect(cls=wavelink.Player)

    tracks = await wavelink.Playable.search(search)
    if not tracks:
        return await ctx.send("Gaana nahi mila 😢")

    track = tracks[0]
    await vc.play(track)
    await ctx.send(f'Baja raha: **{track.title}** 🎵\nNode: `{vc.node.identifier}`')

@bot.command()
async def stop(ctx):
    vc: wavelink.Player = ctx.voice_client
    if vc:
        await vc.disconnect()
        await ctx.send("Band kar diya ⏹️")

@bot.command()
async def node(ctx):
    vc: wavelink.Player = ctx.voice_client
    if vc:
        await ctx.send(f'Current Node: `{vc.node.identifier}`')
    else:
        await ctx.send("VC me nahi hu")

bot.run(os.getenv('DISCORD_TOKEN'))
