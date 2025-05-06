import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import asyncio
import os

# Use your Render variable here
KEY = os.getenv("KEY")

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

POINTS_FILE = "points.json"
REWARDS_FILE = "rewards.json"

GUILD_ID = int(os.getenv("GUILD_ID"))
 # Replace with your actual server ID

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
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Logged in as {bot.user}")

### --- USER COMMANDS --- ###

@tree.command(name="help", description="Show all commands", guild=discord.Object(id=GUILD_ID))
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
    if not rewards:
        return await interaction.response.send_message("No rewards to redeem.")

    options = [discord.SelectOption(label=name, description=f"{data['price']} pts")
               for name, data in rewards.items() if data["stock"] > 0]

    if not options:
        return await interaction.response.send_message("All rewards are out of stock.")

    class RewardMenu(discord.ui.View):
        @discord.ui.select(placeholder="Select a reward to redeem", options=options)
        async def select_callback(self, interaction2: discord.Interaction, select: discord.ui.Select):
            reward_name = select.values[0]
            reward = rewards[reward_name]
            if user_points < reward["price"]:
                await interaction2.response.send_message("You don't have enough points.", ephemeral=True)
                return
            points[user_id] -= reward["price"]
            reward["stock"] -= 1
            save_json(POINTS_FILE, points)
            save_json(REWARDS_FILE, rewards)
            log_channel = discord.utils.get(interaction.guild.channels, name="redeem_logs")
            await interaction2.response.send_message(f"You redeemed **{reward_name}**!", ephemeral=True)
            if log_channel:
                await log_channel.send(f"{interaction.user.mention} redeemed **{reward_name}**.")

    await interaction.response.send_message("Choose a reward:", view=RewardMenu(), ephemeral=True)

### --- OWNER COMMANDS --- ###

@tree.command(name="give", description="Give points to a user", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
@app_commands.describe(user="The user", amount="Points to give")
async def give(interaction: discord.Interaction, user: discord.Member, amount: int):
    points[str(user.id)] = points.get(str(user.id), 0) + amount
    save_json(POINTS_FILE, points)
    await interaction.response.send_message(f"Gave **{amount}** points to {user.mention}.")

@tree.command(name="give_everyone", description="Give points to all members", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
@app_commands.describe(amount="Points to give to everyone")
async def give_everyone(interaction: discord.Interaction, amount: int):
    for member in interaction.guild.members:
        if not member.bot:
            points[str(member.id)] = points.get(str(member.id), 0) + amount
    save_json(POINTS_FILE, points)
    await interaction.response.send_message(f"Gave **{amount}** points to everyone.")

@tree.command(name="remove_points", description="Remove points from a user", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
@app_commands.describe(user="User", amount="Points to remove")
async def remove(interaction: discord.Interaction, user: discord.Member, amount: int):
    points[str(user.id)] = max(0, points.get(str(user.id), 0) - amount)
    save_json(POINTS_FILE, points)
    await interaction.response.send_message(f"Removed **{amount}** points from {user.mention}.")

@tree.command(name="raw_points", description="Show all members and their points", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
async def raw_points(interaction: discord.Interaction):
    msg = "**All Members Points:**\n"
    for uid, pts in points.items():
        member = interaction.guild.get_member(int(uid))
        name = member.display_name if member else "Unknown"
        msg += f"{name}: {pts}\n"
    await interaction.response.send_message(msg)

@tree.command(name="add_reward", description="Add a new reward", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
async def add_reward(interaction: discord.Interaction, name: str, price: int, stock: int):
    rewards[name] = {"price": price, "stock": stock}
    save_json(REWARDS_FILE, rewards)
    await interaction.response.send_message(f"Added reward **{name}** for {price} points.")

@tree.command(name="add_stock", description="Add stock to a reward", guild=discord.Object(id=GUILD_ID))
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

@tree.command(name="drop", description="Drop points for fastest user", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
async def drop(interaction: discord.Interaction, amount: int):
    class DropView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)
            self.claimed = False

        @discord.ui.button(label="Pick up", style=discord.ButtonStyle.green)
        async def pickup(self, interaction2: discord.Interaction, button: discord.ui.Button):
            if self.claimed:
                await interaction2.response.send_message("Someone already picked it up!", ephemeral=True)
            else:
                self.claimed = True
                user_id = str(interaction2.user.id)
                points[user_id] = points.get(user_id, 0) + amount
                save_json(POINTS_FILE, points)
                await interaction2.response.edit_message(content=f"{interaction2.user.mention} picked up **{amount}** points!", view=None)

    await interaction.response.send_message(f"**Exida just dropped {amount} points!**", view=DropView())

# Start bot
bot.run(KEY)
