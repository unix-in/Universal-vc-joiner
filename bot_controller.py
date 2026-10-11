import asyncio
import os
import sys
import discord
from discord import app_commands
from discord.ext import commands

from core.config import ConfigManager
from core.manager import VoiceJoinerManager

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
config_mgr = ConfigManager()
manager = VoiceJoinerManager(config_mgr)

vc_group = app_commands.Group(name="vc", description="Voice Joiner & Presence Controller")

@vc_group.command(name="join", description="Make accounts join a voice channel")
@app_commands.describe(channel="Voice Channel to join", account="Account name/index or 'all'")
async def slash_join(interaction: discord.Interaction, channel: discord.VoiceChannel, account: str = "all"):
    await interaction.response.defer(ephemeral=True)
    joined = await manager.join_vc(selector=account, channel_id=str(channel.id), guild_id=str(channel.guild.id))
    if joined:
        await interaction.followup.send(f"Joined **{channel.name}** (`{channel.id}`) on: {', '.join(joined)}")
    else:
        await interaction.followup.send(f"Failed to join voice channel for '{account}'.")

@vc_group.command(name="leave", description="Make accounts leave their voice channels")
@app_commands.describe(account="Account name/index or 'all'")
async def slash_leave(interaction: discord.Interaction, account: str = "all"):
    await interaction.response.defer(ephemeral=True)
    left = await manager.leave_vc(selector=account)
    if left:
        await interaction.followup.send(f"Disconnected from VC: {', '.join(left)}")
    else:
        await interaction.followup.send(f"No active VC sessions found for '{account}'.")

@vc_group.command(name="stream", description="Set account presence to Streaming in VC")
@app_commands.describe(account="Account name/index or 'all'", title="Stream Title / Game", twitch_url="Twitch URL")
async def slash_stream(interaction: discord.Interaction, account: str, title: str, twitch_url: str = "https://www.twitch.tv/discord"):
    await interaction.response.defer(ephemeral=True)
    updated = await manager.set_stream(selector=account, title=title, url=twitch_url)
    if updated:
        await interaction.followup.send(f"Streaming presence **{title}** active on: {', '.join(updated)}")
    else:
        await interaction.followup.send(f"Account '{account}' not found.")

@vc_group.command(name="music", description="Set account presence to Listening to Music (Spotify)")
@app_commands.describe(account="Account name/index or 'all'", song="Song name", artist="Artist name")
async def slash_music(interaction: discord.Interaction, account: str, song: str, artist: str = ""):
    await interaction.response.defer(ephemeral=True)
    updated = await manager.set_music(selector=account, song=song, artist=artist)
    if updated:
        await interaction.followup.send(f"Spotify presence **{song}** by *{artist}* active on: {', '.join(updated)}")
    else:
        await interaction.followup.send(f"Account '{account}' not found.")

@vc_group.command(name="status", description="Set status (online, idle, dnd, invisible)")
@app_commands.describe(account="Account name/index or 'all'", status="Online, idle, dnd, or invisible")
@app_commands.choices(status=[
    app_commands.Choice(name="Online", value="online"),
    app_commands.Choice(name="Idle", value="idle"),
    app_commands.Choice(name="Do Not Disturb", value="dnd"),
    app_commands.Choice(name="Invisible", value="invisible")
])
async def slash_status(interaction: discord.Interaction, account: str, status: app_commands.Choice[str]):
    await interaction.response.defer(ephemeral=True)
    updated = await manager.set_status(selector=account, status=status.value)
    if updated:
        await interaction.followup.send(f"Status updated to **{status.name}** on: {', '.join(updated)}")
    else:
        await interaction.followup.send(f"Account '{account}' not found.")

@vc_group.command(name="list", description="List all configured accounts and their statuses")
async def slash_list(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    embed = discord.Embed(title="Voice Joiner - Account Statuses", color=0x5865F2)
    clients = manager.get_all_clients()
    if not clients:
        embed.description = "No accounts currently loaded. Configure accounts in config.json."
    else:
        for client in clients:
            if client.in_vc:
                state_text = "In VC"
            elif client.state_desc == "READY":
                state_text = "Connected"
            else:
                state_text = "Offline"

            activity = client.activity or {}
            act_type = activity.get("type", "none").capitalize()
            act_name = activity.get("name", "None")
            embed.add_field(
                name=f"{client.name} ({client.username})",
                value=f"**State:** {state_text}\n**VC:** `{client.channel_id or 'None'}`\n**Status:** `{client.status}`\n**Activity:** `{act_type}: {act_name}`",
                inline=False
            )
    embed.set_footer(text="Voice Joiner • Developed by Saint (Discord: xqfb)")
    await interaction.followup.send(embed=embed)

bot.tree.add_command(vc_group)

@bot.event
async def on_ready():
    print(f"[Bot Controller] Logged in as {bot.user.name} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"[Bot Controller] Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"[Bot Controller] Failed to sync slash commands: {e}")
    await manager.start()

def main():
    conf = config_mgr.data.get("controller_bot", {})
    token = conf.get("bot_token", "").strip()
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        print("[Bot Controller] No Discord Bot token configured in config.json under 'controller_bot.bot_token'.")
        print("To control via Discord Bot, create a Bot on the Discord Developer Portal and enter its token.")
        print("Otherwise, run 'python main.py' to use the interactive Terminal CLI interface.")
        return

    bot.run(token)

if __name__ == "__main__":
    main()
