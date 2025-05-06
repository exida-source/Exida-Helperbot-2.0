import discord
from discord.ext import commands
from discord import app_commands
import json
import asyncio
import os
import threading
from flask import Flask

# --- Config ---
KEY = os.getenv("KEY")
GUILD_ID = int(os.getenv("GUILD_ID"))  # Replace with actual server ID or environment variable
POINTS_FILE = "points.json"
REWARDS_FILE = "rewards.json"

# --- Flask Setup (for Render, etc.) ---
app = Flask(__name__)
def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

# --- Discord Setup ---
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# --- JSON Handling ---
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

# --- Permissions ---
def is_owner(interaction: discord.Interaction):
    return any(role.name.lower() == "owner" for role in interaction.user.roles)

# --- On Ready ---
@bot.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Bot is ready as {bot.user}!")

# --- User Commands ---
@tree.command(name="help", description="Show all commands", guild=discord.Object(id=GUILD_ID))
async def help_cmd(interaction: discord.Interaction):
    help_text = """
**User Commands**
- `/ping` - Test the bot.
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
    await interaction.response.send_message(help_text, ephemeral=True)

@tree.command(name="ping", description="Ping the bot", guild=discord.Object(id=GUILD_ID))
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong!")

@tree.command(name="points", description="Check a user's points", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="The user to check")
async def points_cmd(interaction: discord.Interaction, user: discord.Member):
    user_id = str(user.id)
    user_points = points.get(user_id, 0)
    await interaction.response.send_message(f"{user.mention} has **{user_points}** points.")

@tree.command(name="leaderboard", description="Show top 10 users", guild=discord.Object(id=GUILD_ID))
async def leaderboard(interaction: discord.Interaction):
    sorted_points = sorted(points.items(), key=lambda x: x[1], reverse=True)[:10]
    msg = "**Top 10 Users:**\n"
    for i, (uid, pts) in enumerate(sorted_points, start=1):
        member = interaction.guild.get_member(int(uid))
        name = member.display_name if member else "Unknown"
        msg += f"{i}. {name} — {pts} points\n"
    await interaction.response.send_message(msg)

@tree.command(name="rewards", description="List available rewards", guild=discord.Object(id=GUILD_ID))
async def rewards_cmd(interaction: discord.Interaction):
    if not rewards:
        return await interaction.response.send_message("No rewards available yet.")
    msg = "**Rewards Available:**\n"
    for name, data in rewards.items():
        msg += f"- **{name}**: {data['price']} points ({data['stock']} in stock)\n"
    await interaction.response.send_message(msg)

@tree.command(name="redeem", description="Redeem a reward", guild=discord.Object(id=GUILD_ID))
async def redeem(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    user_points = points.get(user_id, 0)

    options = [
        discord.SelectOption(label=name, description=f"{data['price']} pts")
        for name, data in rewards.items() if data["stock"] > 0
    ]

    if not options:
        return await interaction.response.send_message("All rewards are out of stock.")

    class RewardMenu(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=30)

            self.select = discord.ui.Select(
                placeholder="Select a reward",
                options=options
            )
            self.select.callback = self.select_callback
            self.add_item(self.select)

        async def select_callback(self, interaction2: discord.Interaction):
            reward_name = self.select.values[0]
            reward = rewards[reward_name]
            if user_points < reward["price"]:
                await interaction2.response.send_message("Not enough points.", ephemeral=True)
                return
            points[user_id] -= reward["price"]
            reward["stock"] -= 1
            save_json(POINTS_FILE, points)
            save_json(REWARDS_FILE, rewards)
            log_channel = discord.utils.get(interaction.guild.channels, name="redeem_logs")
            await interaction2.response.send_message(f"You redeemed **{reward_name}**!")
            if log_channel:
                await log_channel.send(f"{interaction.user.mention} redeemed **{reward_name}**.")

    await interaction.response.send_message("Choose a reward:", view=RewardMenu(), ephemeral=True)

# --- Owner Commands ---
@tree.command(name="give", description="Give points to a user", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
@app_commands.describe(user="User", amount="Points to give")
async def give(interaction: discord.Interaction, user: discord.Member, amount: int):
    points[str(user.id)] = points.get(str(user.id), 0) + amount
    save_json(POINTS_FILE, points)
    await interaction.response.send_message(f"Gave **{amount}** points to {user.mention}.")

@tree.command(name="give_everyone", description="Give points to all users", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
@app_commands.describe(amount="Amount of points to give")
async def give_everyone(interaction: discord.Interaction, amount: int):
    for member in interaction.guild.members:
        if not member.bot:
            points[str(member.id)] = points.get(str(member.id), 0) + amount
    save_json(POINTS_FILE, points)
    await interaction.response.send_message(f"Gave **{amount}** points to everyone.")

@tree.command(name="remove_points", description="Remove points from a user", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
async def remove_points(interaction: discord.Interaction, user: discord.Member, amount: int):
    points[str(user.id)] = max(0, points.get(str(user.id), 0) - amount)
    save_json(POINTS_FILE, points)
    await interaction.response.send_message(f"Removed **{amount}** points from {user.mention}.")

@tree.command(name="raw_points", description="View raw points of all users", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
async def raw_points(interaction: discord.Interaction):
    msg = "**All Users and Points:**\n"
    for uid, pts in points.items():
        member = interaction.guild.get_member(int(uid))
        name = member.display_name if member else "Unknown"
        msg += f"{name}: {pts}\n"
    await interaction.response.send_message(msg)

@tree.command(name="add_reward", description="Add a reward", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
async def add_reward(interaction: discord.Interaction, name: str, price: int, stock: int):
    rewards[name] = {"price": price, "stock": stock}
    save_json(REWARDS_FILE, rewards)
    await interaction.response.send_message(f"Added reward **{name}**.")

@tree.command(name="add_stock", description="Increase stock of a reward", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
async def add_stock(interaction: discord.Interaction, name: str, amount: int):
    if name not in rewards:
        return await interaction.response.send_message("Reward not found.")
    rewards[name]["stock"] += amount
    save_json(REWARDS_FILE, rewards)
    await interaction.response.send_message(f"Added {amount} stock to **{name}**.")

@tree.command(name="delete_reward", description="Delete a reward", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
async def delete_reward(interaction: discord.Interaction, name: str):
    if rewards.pop(name, None):
        save_json(REWARDS_FILE, rewards)
        await interaction.response.send_message(f"Deleted reward **{name}**.")
    else:
        await interaction.response.send_message("Reward not found.")

@tree.command(name="drop", description="Drop points for the fastest user", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
async def drop(interaction: discord.Interaction, amount: int):
    class DropView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)
            self.claimed = False

        @discord.ui.button(label="Pick up", style=discord.ButtonStyle.green)
        async def pickup(self, interaction2: discord.Interaction, button: discord.ui.Button):
            if self.claimed:
                await interaction2.response.send_message("Already claimed!", ephemeral=True)
            else:
                self.claimed = True
                user_id = str(interaction2.user.id)
                points[user_id] = points.get(user_id, 0) + amount
                save_json(POINTS_FILE, points)
                await interaction2.response.edit_message(content=f"{interaction2.user.mention} picked up **{amount}** points!", view=None)

    await interaction.response.send_message(f"**{amount} points dropped! First to click gets them!**", view=DropView())

# --- Run both Flask and Bot ---
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run(KEY)
