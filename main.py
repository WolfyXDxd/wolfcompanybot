import discord
from discord.ext import commands
import wavelink
import logging
from dotenv import load_dotenv
import os
import asyncio
from collections import deque
import webserver

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

# Configuración del logging
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='-', intents=intents, help_command=None)

# Sistema de colas de música por servidor
music_queues = {}

class MusicQueue:
    def __init__(self):
        self.queue = deque()
        self.current = None
    
    def add(self, track):
        self.queue.append(track)
    
    def next(self):
        if len(self.queue) > 0:
            return self.queue.popleft()
        return None
    
    def clear(self):
        self.queue.clear()
        self.current = None
    
    def get_queue(self):
        return list(self.queue)

def get_music_queue(guild_id):
    if guild_id not in music_queues:
        music_queues[guild_id] = MusicQueue()
    return music_queues[guild_id]

# Lista de comandos para el help
comandos = {
    "-help": "Muestra este mensaje de ayuda",
    "-assign @usuario": "Asigna el rol x a un usuario (Solo Admin)",
    "-remove @usuario": "Elimina el rol x a un usuario (Solo Admin)",
    "-dm @usuario mensaje": "El bot envía un mensaje directo al usuario mencionado",
    "-hola": "El bot te saluda",
    "-secret": "Comando secreto (Solo Owner del servidor)",
    "-join": "El bot se une a tu canal de voz",
    "-play <búsqueda>": "Reproduce música de YouTube o la añade a la cola",
    "-pause": "Pausa la música actual",
    "-resume": "Reanuda la música pausada",
    "-stop": "Detiene la música y desconecta el bot",
    "-skip": "Salta la canción actual",
    "-queue": "Muestra la cola de reproducción",
    "-clear": "Limpia la cola de reproducción",
    "-np": "Muestra la canción actual",
    "-volume <0-100>": "Ajusta el volumen"
}

@bot.event
async def on_ready():
    # Nodo más estable y confiable
    nodes = [wavelink.Node(uri='https://lavalink.jirayu.net:443', password='youshallnotpass')]
    
    try:
        await wavelink.Pool.connect(nodes=nodes, client=bot)
        print(f"✅ Conectado a Lavalink: lavalink.jirayu.net")
    except Exception as e:
        print(f"❌ Error conectando a Lavalink: {e}")
    
    await bot.change_presence(
        status=discord.Status.online,  
        activity=discord.Activity(
            type=discord.ActivityType.listening, 
            name="-help"
        )
    )
    print(f"Tamo redi loco, {bot.user.name}")
    print(f"Conectado a {len(bot.guilds)} servidor(es)")

@bot.event
async def on_wavelink_track_end(payload: wavelink.TrackEndEventPayload):
    """Se ejecuta cuando termina una canción"""
    player = payload.player
    if not player:
        return
    
    queue = get_music_queue(player.guild.id)
    
    # Reproducir siguiente canción
    if len(queue.queue) > 0:
        next_track = queue.next()
        queue.current = next_track
        await player.play(next_track)
        
        channel = player.guild.get_channel(player.channel.id)
        if channel:
            embed = discord.Embed(
                title="🎵 Reproduciendo",
                description=f"**{next_track.title}**",
                color=discord.Color.green()
            )
            await channel.send(embed=embed)
    else:
        queue.current = None

@bot.command(aliases=["h", "ayuda", "comandos"])
async def help(ctx):
    embed = discord.Embed(
        title="📋 Lista de Comandos", 
        description="Aquí están todos los comandos disponibles:", 
        color=discord.Color.blue()
    )
    
    for comando, descripcion in comandos.items():
        embed.add_field(name=comando, value=descripcion, inline=False)
    
    embed.set_footer(text=f"Prefijo: {bot.command_prefix}")
    await ctx.send(embed=embed)

@bot.command()
async def hola(ctx):
    await ctx.send(f"Hola {ctx.author.mention}! 👋")

@bot.command(aliases=["asignar"])
@commands.has_permissions(administrator=True)
async def assign(ctx, member: discord.Member):
    if member is None:
        await ctx.send("No pude encontrar a ese usuario")
        return
    
    if member.bot:
        await ctx.send("No puedo asignar roles a bots")
        return
    
    role = discord.utils.get(ctx.guild.roles, name="x")
    
    if role is None:
        await ctx.send("El rol 'x' no existe en este servidor")
        roles_list = [r.name for r in ctx.guild.roles]
        print(f"Roles disponibles: {roles_list}")
        return
    
    if role in member.roles:
        await ctx.send(f"{member.mention} ya tiene el rol **{role.name}**")
        return
    
    try:
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send("El bot no tiene permisos para gestionar roles")
            return
        
        if role.position >= ctx.guild.me.top_role.position:
            await ctx.send("El rol del bot debe estar por encima del rol a asignar en la jerarquía")
            return
        
        await member.add_roles(role)
        await ctx.send(f"✅ {ctx.author.mention} el rol **{role.name}** ha sido añadido correctamente a {member.mention}")
        
    except discord.Forbidden:
        await ctx.send("No tengo permisos suficientes para asignar ese rol")
    except Exception as e:
        await ctx.send(f"Error al asignar el rol: {str(e)}")
        print(f"Error: {e}")

@assign.error
async def assign_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ No tienes permisos para ejecutar ese comando")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ No se ha encontrado al miembro")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Debes mencionar al usuario al cual le quieres asignar el rol\nUso: `-assign @usuario`")

@bot.command(aliases=["remover"])
@commands.has_permissions(administrator=True)
async def remove(ctx, member: discord.Member):
    if member is None:
        await ctx.send("No pude encontrar a ese usuario")
        return
    
    if member.bot:
        await ctx.send("No puedo remover roles a bots")
        return
    
    role = discord.utils.get(ctx.guild.roles, name="x")
    
    if role is None:
        await ctx.send("El rol 'x' no existe en este servidor")
        roles_list = [r.name for r in ctx.guild.roles]
        print(f"Roles disponibles: {roles_list}")
        return
    
    if role not in member.roles:
        await ctx.send(f"{member.mention} no tiene el rol **{role.name}**")
        return
    
    try:
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send("El bot no tiene permisos para gestionar roles")
            return
        
        if role.position >= ctx.guild.me.top_role.position:
            await ctx.send("El rol del bot debe estar por encima del rol a remover en la jerarquía")
            return
        
        await member.remove_roles(role)
        await ctx.send(f"✅ {ctx.author.mention} el rol **{role.name}** ha sido removido correctamente de {member.mention}")
        
    except discord.Forbidden:
        await ctx.send("No tengo permisos suficientes para remover ese rol")
    except Exception as e:
        await ctx.send(f"Error al remover el rol: {str(e)}")
        print(f"Error: {e}")

@remove.error
async def remove_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ No tienes permisos para ejecutar ese comando")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ No se ha encontrado al miembro")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Debes mencionar al usuario al cual le quieres remover el rol\nUso: `-remove @usuario`")

@bot.command()
@commands.has_role("Owner del servidor")
async def secret(ctx):
    await ctx.send("🔐 Test del rol secreto completado!")

@secret.error
async def secret_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ No tienes el rol necesario para ejecutar este comando")

@bot.command()
async def dm(ctx, member: discord.Member, *, msg):
    if member.bot:
        await ctx.send("No puedo enviar mensajes a otros bots")
        return
    
    if member.id == ctx.author.id:
        await ctx.send("No puedes enviarte un DM a ti mismo usando este comando")
        return
    
    try:
        await member.send(msg)
        await ctx.author.send(f"✅ El mensaje se envió correctamente a **{member.name}**")
        await ctx.message.delete()
    except discord.Forbidden:
        await ctx.send(f"❌ No puedo enviar mensajes privados a {member.mention}. Puede que tenga los DMs desactivados.")
    except Exception as e:
        await ctx.send(f"❌ Error al enviar el mensaje: {str(e)}")

@dm.error
async def dm_error(ctx, error):
    if isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ No se ha encontrado al miembro")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Uso correcto: `-dm @usuario tu mensaje aquí`")

# ==================== COMANDOS DE MÚSICA CON WAVELINK ====================

@bot.command(aliases=["j", "connect"])
async def join(ctx):
    if not ctx.author.voice:
        await ctx.send("❌ ¡Debes estar en un canal de voz!")
        return
    
    channel = ctx.author.voice.channel
    
    if ctx.voice_client:
        await ctx.voice_client.move_to(channel)
        await ctx.send(f"🔊 Movido a **{channel.name}**")
    else:
        await channel.connect(cls=wavelink.Player)
        await ctx.send(f"🔊 Conectado a **{channel.name}**")

@bot.command(aliases=["p"])
async def play(ctx, *, search: str):
    if not ctx.author.voice:
        await ctx.send("❌ Debes estar en un canal de voz para usar este comando")
        return
    
    if not ctx.voice_client:
        vc: wavelink.Player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
    else:
        vc: wavelink.Player = ctx.voice_client
    
    await ctx.send("🔍 Buscando...")
    
    try:
        # Buscar en YouTube
        tracks = await wavelink.Playable.search(search)
        
        if not tracks:
            await ctx.send("❌ No se encontró ninguna canción")
            return
        
        track = tracks[0]
        queue = get_music_queue(ctx.guild.id)
        
        # Si no está reproduciendo nada, reproduce inmediatamente
        if not vc.playing:
            queue.current = track
            await vc.play(track)
            
            embed = discord.Embed(
                title="🎵 Reproduciendo",
                description=f"**{track.title}**",
                color=discord.Color.green()
            )
            embed.add_field(name="Duración", value=f"{track.length // 60000}:{(track.length // 1000) % 60:02d}", inline=True)
            embed.add_field(name="Autor", value=track.author, inline=True)
            await ctx.send(embed=embed)
        else:
            # Agregar a la cola
            queue.add(track)
            
            embed = discord.Embed(
                title="➕ Añadido a la cola",
                description=f"**{track.title}**",
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Posición en la cola: {len(queue.queue)}")
            await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")
        print(f"Error detallado en play: {type(e).__name__}: {e}")

@bot.command(aliases=["q", "lista"])
async def queue(ctx):
    queue_obj = get_music_queue(ctx.guild.id)
    
    if not queue_obj.current and len(queue_obj.queue) == 0:
        await ctx.send("❌ La cola está vacía")
        return
    
    embed = discord.Embed(
        title="🎵 Cola de Reproducción",
        color=discord.Color.blue()
    )
    
    if queue_obj.current:
        embed.add_field(
            name="▶️ Reproduciendo ahora:",
            value=f"**{queue_obj.current.title}**",
            inline=False
        )
    
    if len(queue_obj.queue) > 0:
        queue_list = queue_obj.get_queue()
        songs_text = "\n".join([f"{i+1}. {track.title}" for i, track in enumerate(queue_list[:10])])
        
        if len(queue_list) > 10:
            songs_text += f"\n\n... y {len(queue_list) - 10} más"
        
        embed.add_field(
            name=f"📋 Próximas canciones ({len(queue_list)}):",
            value=songs_text,
            inline=False
        )
    else:
        embed.add_field(
            name="📋 Próximas canciones:",
            value="No hay canciones en la cola",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(aliases=["nowplaying", "current"])
async def np(ctx):
    if not ctx.voice_client or not isinstance(ctx.voice_client, wavelink.Player):
        await ctx.send("❌ No hay música reproduciéndose")
        return
    
    vc: wavelink.Player = ctx.voice_client
    
    if not vc.playing:
        await ctx.send("❌ No hay música reproduciéndose")
        return
    
    track = vc.current
    embed = discord.Embed(
        title="🎵 Reproduciendo ahora",
        description=f"**{track.title}**",
        color=discord.Color.green()
    )
    embed.add_field(name="Autor", value=track.author, inline=True)
    embed.add_field(name="Duración", value=f"{track.length // 60000}:{(track.length // 1000) % 60:02d}", inline=True)
    await ctx.send(embed=embed)

@bot.command(aliases=["c", "limpiar"])
async def clear(ctx):
    queue = get_music_queue(ctx.guild.id)
    queue.clear()
    await ctx.send("🗑️ Cola limpiada")

@bot.command()
async def pause(ctx):
    if not ctx.voice_client or not isinstance(ctx.voice_client, wavelink.Player):
        await ctx.send("❌ No hay música reproduciéndose")
        return
    
    vc: wavelink.Player = ctx.voice_client
    
    if vc.playing:
        await vc.pause(True)
        await ctx.send("⏸️ Música pausada")
    else:
        await ctx.send("❌ No hay música reproduciéndose")

@bot.command()
async def resume(ctx):
    if not ctx.voice_client or not isinstance(ctx.voice_client, wavelink.Player):
        await ctx.send("❌ No hay música reproduciéndose")
        return
    
    vc: wavelink.Player = ctx.voice_client
    
    if vc.paused:
        await vc.pause(False)
        await ctx.send("▶️ Música reanudada")
    else:
        await ctx.send("❌ La música no está pausada")

@bot.command()
async def stop(ctx):
    if not ctx.voice_client:
        await ctx.send("❌ No estoy en un canal de voz")
        return
    
    vc: wavelink.Player = ctx.voice_client
    queue = get_music_queue(ctx.guild.id)
    queue.clear()
    
    await vc.disconnect()
    await ctx.send("⏹️ Música detenida y desconectado del canal")

@bot.command()
async def skip(ctx):
    if not ctx.voice_client or not isinstance(ctx.voice_client, wavelink.Player):
        await ctx.send("❌ No hay música reproduciéndose")
        return
    
    vc: wavelink.Player = ctx.voice_client
    
    if vc.playing:
        await vc.stop()
        await ctx.send("⏭️ Canción saltada")
    else:
        await ctx.send("❌ No hay música reproduciéndose")

@bot.command(aliases=["vol"])
async def volume(ctx, vol: int):
    if not ctx.voice_client or not isinstance(ctx.voice_client, wavelink.Player):
        await ctx.send("❌ No estoy conectado a un canal de voz")
        return
    
    vc: wavelink.Player = ctx.voice_client
    
    if 0 <= vol <= 100:
        await vc.set_volume(vol)
        await ctx.send(f"🔊 Volumen ajustado a **{vol}%**")
    else:
        await ctx.send("❌ El volumen debe estar entre 0 y 100")

# Manejo global de errores
@bot.event
async def on_command_error(ctx, error):
    if hasattr(ctx.command, 'on_error'):
        return
    
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ Comando no encontrado. Usa `-help` para ver los comandos disponibles")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Faltan argumentos. Usa `-help` para ver el uso correcto")
    else:
        print(f"Error no manejado: {error}")

webserver.keep_alive()
bot.run(token, log_handler=handler, log_level=logging.DEBUG)