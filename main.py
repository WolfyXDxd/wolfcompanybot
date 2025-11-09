import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import asyncio
import yt_dlp as youtube_dl
from collections import deque
import webserver

load_dotenv()
token = os.getenv('DISCORD_TOKEN')
cookies = os.getenv("COOKIES")

if cookies:
    # Primero intentamos con replace simple
    cookies_content = cookies.replace("\\n", "\n")
    
    # Si aún tiene \\n literales, intentamos otra vez
    if "\\n" in cookies_content:
        cookies_content = cookies_content.replace("\\\\n", "\n")
    
    try:
        with open("cookies.txt", "w", encoding="utf-8") as f:
            f.write(cookies_content)
        print("✅ Archivo cookies.txt creado correctamente")
        
        # Verificar que se creó correctamente
        with open("cookies.txt", "r", encoding="utf-8") as f:
            lines = f.readlines()
            print(f"📝 Cookies.txt tiene {len(lines)} líneas")
            
    except Exception as e:
        print(f"❌ Error al crear cookies.txt: {e}")
else:
    print("⚠️ No se encontró la variable de entorno COOKIES")

# Configuración del logging
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='-', intents=intents, help_command=None)

# Configuración de youtube_dl
youtube_dl.utils.bug_reports_message = lambda **kwargs: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'force_generic_extractor': False,
    'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
    # Cliente Android para evitar restricciones
    'extractor_args': {
        'youtube': {
            'player_client': ['android'],
            'skip': ['hls', 'dash', 'translated_subs']
        }
    }
}

# Opciones mejoradas de FFmpeg con reconexión
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -bufsize 512k'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

# Sistema de colas de música por servidor
music_queues = {}

class MusicQueue:
    def __init__(self):
        self.queue = deque()
        self.current = None
        self.is_playing = False
    
    def add(self, song):
        self.queue.append(song)
    
    def next(self):
        if len(self.queue) > 0:
            return self.queue.popleft()
        return None
    
    def clear(self):
        self.queue.clear()
        self.current = None
    
    def get_queue(self):
        return list(self.queue)

# Lista de comandos para el help
comandos = {
    "-help": "Muestra este mensaje de ayuda",
    "-assign @usuario": "Asigna el rol x a un usuario (Solo Admin)",
    "-remove @usuario": "Elimina el rol x a un usuario (Solo Admin)",
    "-dm @usuario mensaje": "El bot envía un mensaje directo al usuario mencionado",
    "-hola": "El bot te saluda",
    "-secret": "Comando secreto (Solo Owner del servidor)",
    "-join": "El bot se une a tu canal de voz",
    "-play <url/búsqueda>": "Reproduce música de YouTube o la añade a la cola",
    "-pause": "Pausa la música actual",
    "-resume": "Reanuda la música pausada",
    "-stop": "Detiene la música y desconecta el bot",
    "-skip": "Salta la canción actual",
    "-queue": "Muestra la cola de reproducción",
    "-clear": "Limpia la cola de reproducción",
    "-np": "Muestra la canción actual"
}

@bot.event
async def on_ready():
    await bot.change_presence(
        status=discord.Status.online,  
        activity=discord.Activity(
            type=discord.ActivityType.listening, 
            name="-help"
        )
    )
    print(f"Tamo redi loco, {bot.user.name}")
    print(f"Conectado a {len(bot.guilds)} servidor(es)")

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

# ==================== COMANDOS DE MÚSICA ====================

def get_music_queue(guild_id):
    if guild_id not in music_queues:
        music_queues[guild_id] = MusicQueue()
    return music_queues[guild_id]

async def play_next(ctx):
    queue = get_music_queue(ctx.guild.id)
    
    if len(queue.queue) == 0:
        queue.is_playing = False
        queue.current = None
        await ctx.send("✅ Cola finalizada")
        return
    
    song = queue.next()
    queue.current = song
    queue.is_playing = True
    
    try:
        player = discord.FFmpegPCMAudio(song['url'], **ffmpeg_options)
        
        def after_playing(error):
            if error:
                print(f'Error de reproducción: {error}')
            
            # Reproduce la siguiente canción
            coro = play_next(ctx)
            fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
            try:
                fut.result()
            except Exception as e:
                print(f'Error al reproducir siguiente canción: {e}')
        
        ctx.voice_client.play(player, after=after_playing)
        
        embed = discord.Embed(
            title="🎵 Reproduciendo",
            description=f"**{song['title']}**",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error al reproducir: {str(e)}")
        queue.is_playing = False

@bot.command(aliases=["j", "connect"])
async def join(ctx):
    if not ctx.author.voice:
        await ctx.send("❌ ¡Debes estar en un canal de voz!")
        return
    
    channel = ctx.author.voice.channel
    
    if ctx.voice_client is not None:
        await ctx.voice_client.move_to(channel)
        await ctx.send(f"🔊 Movido a **{channel.name}**")
    else:
        await channel.connect()
        await ctx.send(f"🔊 Conectado a **{channel.name}**")

@bot.command(aliases=["p"])
async def play(ctx, *, search):
    if not ctx.author.voice:
        await ctx.send("❌ Debes estar en un canal de voz para usar este comando")
        return
    
    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()

    await ctx.send("🔍 Buscando...")
    
    try:
        loop = asyncio.get_event_loop()
        
        # Buscar el video
        data = await loop.run_in_executor(
            None, 
            lambda: ytdl.extract_info(f"ytsearch:{search}", download=False)
        )
        
        if 'entries' in data:
            data = data['entries'][0]
        
        song = {
            'url': data['url'],
            'title': data['title'],
            'webpage_url': data.get('webpage_url', '')
        }
        
        queue = get_music_queue(ctx.guild.id)
        
        # Si no hay nada reproduciéndose, reproduce inmediatamente
        if not ctx.voice_client.is_playing() and not queue.is_playing:
            queue.current = song
            queue.is_playing = True
            
            player = discord.FFmpegPCMAudio(song['url'], **ffmpeg_options)
            
            def after_playing(error):
                if error:
                    print(f'Error de reproducción: {error}')
                
                coro = play_next(ctx)
                fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
                try:
                    fut.result()
                except Exception as e:
                    print(f'Error al reproducir siguiente canción: {e}')
            
            ctx.voice_client.play(player, after=after_playing)
            
            embed = discord.Embed(
                title="🎵 Reproduciendo",
                description=f"**{song['title']}**",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        else:
            # Agregar a la cola
            queue.add(song)
            
            embed = discord.Embed(
                title="➕ Añadido a la cola",
                description=f"**{song['title']}**",
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Posición en la cola: {len(queue.queue)}")
            await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")
        print(f"Error detallado: {type(e).__name__}: {e}")

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
            value=f"**{queue_obj.current['title']}**",
            inline=False
        )
    
    if len(queue_obj.queue) > 0:
        queue_list = queue_obj.get_queue()
        songs_text = "\n".join([f"{i+1}. {song['title']}" for i, song in enumerate(queue_list[:10])])
        
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
    queue = get_music_queue(ctx.guild.id)
    
    if not queue.current:
        await ctx.send("❌ No hay música reproduciéndose")
        return
    
    embed = discord.Embed(
        title="🎵 Reproduciendo ahora",
        description=f"**{queue.current['title']}**",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(aliases=["c", "limpiar"])
async def clear(ctx):
    queue = get_music_queue(ctx.guild.id)
    queue.clear()
    await ctx.send("🗑️ Cola limpiada")

@bot.command()
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Música pausada")
    else:
        await ctx.send("❌ No hay música reproduciéndose")

@bot.command()
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Música reanudada")
    else:
        await ctx.send("❌ La música no está pausada")

@bot.command()
async def stop(ctx):
    if ctx.voice_client:
        queue = get_music_queue(ctx.guild.id)
        queue.clear()
        queue.is_playing = False
        await ctx.voice_client.disconnect()
        await ctx.send("⏹️ Música detenida y desconectado del canal")
    else:
        await ctx.send("❌ No estoy en un canal de voz")

@bot.command()
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()  # El callback after_playing se encargará de reproducir la siguiente
        await ctx.send("⏭️ Canción saltada")
    else:
        await ctx.send("❌ No hay música reproduciéndose")

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