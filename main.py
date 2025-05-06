import discord
from discord.ext import commands
from discord import app_commands
import json
import asyncio
import os
import threading
from flask import Flask

KEY = os.getenv("KEY")
GUILD_ID = int(os.getenv("GUILD_ID"))

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
app = Flask(__name__)

POINTS_FILE = "points.json"
REWARDS_FILE = "rewards.json"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

def run_discord_bot():
    bot.run(KEY)

def load_json(filename):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

points = load_json(POINTS_FILE)
rewards = load_json(REWARDS_FILE)

def is_owner(interaction: discord.Interaction):
    return any(role.name == "Owner" for role in interaction.user.roles)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

class MyClient(commands.Bot):
    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)

        @app_commands.command(name="help", description="Show all commands")
        async def help_cmd(interaction: discord.Interaction):
            help_text = """
**User Commands**
- `/points [user]` - Check a user’s points.
- `/leaderboard` - View top 10 point holders.
- `/rewards` - View available rewards.
- `/redeem` - Redeem a reward.

**Owner Commands**
- `/give [user] [amount]` - Give points to a user.
- `/give_everyone [amount]` - Give points to everyone.
- `/remove_points [user] [amount]` - Remove points.
- `/raw_points` - List all users and their points.
- `/add_reward [name] [price] [stock]` - Add a reward.
- `/add_stock [reward] [amount]` - Increase reward stock.
- `/delete_reward [name]` - Delete a reward.
- `/drop [amount]` - Drop points for fastest user to grab.
"""
            await interaction.response.send_message(help_text)

        # Define all your other commands here...

        self.tree.add_command(help_cmd, guild=guild)
        # Add the rest of your commands to the tree similarly...

        await self.tree.sync(guild=guild)

bot = MyClient(command_prefix="!", intents=intents)

# Start both Flask and bot
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    run_discord_bot()
