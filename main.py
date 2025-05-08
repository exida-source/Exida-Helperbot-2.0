import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import asyncio
import os
import threading
from flask import Flask
KEY = os.getenv("KEY")
GUILD_ID = int(os.getenv("GUILD_ID"))
DB_FILE = "data.db"

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree
app = Flask(__name__)

def load_json(filename):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

# Run Flask for uptime
def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
@app.route("/")
def home():
    return "Bot is alive!"

# --- SQLite Setup ---
async def setup_database():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS points (
                user_id TEXT PRIMARY KEY,
                amount INTEGER NOT NULL
            );
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rewards (
                name TEXT PRIMARY KEY,
                price INTEGER NOT NULL,
                stock INTEGER NOT NULL
            );
        """)
        await db.commit()

KEYS_FILE = "keys.json"
keys_data = load_json(KEYS_FILE)








# Utility functions
async def get_points(user_id):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT amount FROM points WHERE user_id = ?", (str(user_id),)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def set_points(user_id, amount):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT OR REPLACE INTO points (user_id, amount) VALUES (?, ?)", (str(user_id), amount))
        await db.commit()

async def add_points(user_id, amount):
    current = await get_points(user_id)
    await set_points(user_id, current + amount)

async def get_all_points():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT user_id, amount FROM points ORDER BY amount DESC") as cursor:
            return await cursor.fetchall()

async def get_rewards():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT name, price, stock FROM rewards") as cursor:
            return await cursor.fetchall()

async def get_reward(name):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT price, stock FROM rewards WHERE name = ?", (name,)) as cursor:
            return await cursor.fetchone()

async def update_reward(name, stock=None, price=None):
    async with aiosqlite.connect(DB_FILE) as db:
        if stock is not None:
            await db.execute("UPDATE rewards SET stock = ? WHERE name = ?", (stock, name))
        if price is not None:
            await db.execute("UPDATE rewards SET price = ? WHERE name = ?", (price, name))
        await db.commit()

async def create_reward(name, price, stock):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT OR REPLACE INTO rewards (name, price, stock) VALUES (?, ?, ?)", (name, price, stock))
        await db.commit()

async def delete_reward(name):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM rewards WHERE name = ?", (name,))
        await db.commit()

# Permissions
def is_owner(interaction: discord.Interaction):
    return any(role.name == "Owner" for role in interaction.user.roles)

# Commands
@tree.command(name="help", description="Show all commands", guild=discord.Object(id=GUILD_ID))
async def help_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("""
**User Commands**
- `/points [user]` - Check a user’s points.
- `/leaderboard` - View top 10 point holders.
- `/rewards` - View available rewards.
- `/redeem` - Redeem a reward.

**Owner Commands**
- `/give [user] [amount]`
- `/give_everyone [amount]`
- `/remove_points [user] [amount]`
- `/raw_points`
- `/add_reward [name] [price] [stock]`
- `/add_stock [reward] [amount]`
- `/delete_reward [name]`
- `/drop [amount]`
""", ephemeral=True)

@tree.command(name="generate_key", description="Generate a redeemable key for mystery gift", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
@app_commands.describe(reward_pool="Describe the reward pool (e.g. 'Points: 100-300; Role: VIP')")
async def generate_key(interaction: discord.Interaction, reward_pool: str):
    import secrets
    key = secrets.token_hex(4).upper()
    keys_data[key] = {
        "reward_pool": reward_pool,
        "used": False
    }
    save_json(KEYS_FILE, keys_data)
    await interaction.response.send_message(f"✅ Key generated: `{key}`\nReward Pool: {reward_pool}", ephemeral=True)
@tree.command(name="create_mystery", description="Create a mystery gift box that requires a key", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
async def create_mystery(interaction: discord.Interaction):
    class KeyModal(discord.ui.Modal, title="Enter Your Key"):
        key_input = discord.ui.TextInput(label="Mystery Key", placeholder="Enter the code provided", required=True)

        async def on_submit(self, interaction2: discord.Interaction):
            key = self.key_input.value.strip().upper()
            if key not in keys_data:
                await interaction2.response.send_message("❌ Invalid key.", ephemeral=True)
                return
            if keys_data[key]["used"]:
                await interaction2.response.send_message("❌ This key has already been used.", ephemeral=True)
                return

            keys_data[key]["used"] = True
            save_json(KEYS_FILE, keys_data)

            # Parse reward
            reward_pool = keys_data[key]["reward_pool"]
            msg = f"🎁 {interaction2.user.mention} opened the Mystery Box and received:\n"
            if "Points:" in reward_pool:
                import random
                try:
                    points_range = reward_pool.split("Points:")[1].split(";")[0].strip()
                    low, high = map(int, points_range.split("-"))
                    reward = random.randint(low, high)
                    user_id = str(interaction2.user.id)
                    points[user_id] = points.get(user_id, 0) + reward
                    save_json(POINTS_FILE, points)
                    msg += f"- 💰 **{reward} Points**\n"
                except:
                    pass

            if "Role:" in reward_pool:
                try:
                    role_name = reward_pool.split("Role:")[1].split(";")[0].strip()
                    role = discord.utils.get(interaction2.guild.roles, name=role_name)
                    if role:
                        await interaction2.user.add_roles(role)
                        msg += f"- 🏷️ **{role.mention}** role\n"
                except:
                    pass

            await interaction2.response.send_message(msg, ephemeral=True)

    class MysteryView(discord.ui.View):
        @discord.ui.button(label="🎁 Open Mystery Box", style=discord.ButtonStyle.blurple)
        async def open_box(self, interaction2: discord.Interaction, button: discord.ui.Button):
            await interaction2.response.send_modal(KeyModal())

    await interaction.response.send_message("🎉 **A Mystery Gift Box has appeared!**\nUse your key to unlock a surprise reward!", view=MysteryView())


@tree.command(name="points", description="Check a user's points", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(user="The user to check")
async def points_cmd(interaction: discord.Interaction, user: discord.Member):
    pts = await get_points(user.id)
    await interaction.response.send_message(f"{user.mention} has **{pts}** points.")

@tree.command(name="leaderboard", description="Show top 10 users", guild=discord.Object(id=GUILD_ID))
async def leaderboard(interaction: discord.Interaction):
    data = await get_all_points()
    msg = "**Top 10 Users:**\n"
    for i, (uid, amt) in enumerate(data[:10], 1):
        member = interaction.guild.get_member(int(uid))
        name = member.display_name if member else "Unknown"
        msg += f"{i}. {name} — {amt} points\n"
    await interaction.response.send_message(msg)

@tree.command(name="rewards", description="List available rewards", guild=discord.Object(id=GUILD_ID))
async def rewards_cmd(interaction: discord.Interaction):
    data = await get_rewards()
    if not data:
        return await interaction.response.send_message("No rewards available.")
    msg = "**Rewards Available:**\n"
    for name, price, stock in data:
        msg += f"- **{name}**: {price} points ({stock} in stock)\n"
    await interaction.response.send_message(msg)

@tree.command(name="redeem", description="Redeem a reward", guild=discord.Object(id=GUILD_ID))
async def redeem(interaction: discord.Interaction):
    rewards = await get_rewards()
    options = [discord.SelectOption(label=name, description=f"{price} pts") for name, price, stock in rewards if stock > 0]
    if not options:
        return await interaction.response.send_message("All rewards are out of stock.")

    user_id = str(interaction.user.id)
    user_points = await get_points(user_id)

    class RewardMenu(discord.ui.View):
        @discord.ui.select(placeholder="Select a reward to redeem", options=options)
        async def select_callback(self, interaction2: discord.Interaction, select: discord.ui.Select):
            reward_name = select.values[0]
            reward = await get_reward(reward_name)
            if not reward:
                return await interaction2.response.send_message("Reward not found.", ephemeral=True)
            price, stock = reward
            if user_points < price:
                return await interaction2.response.send_message("Not enough points.", ephemeral=True)

            await set_points(user_id, user_points - price)
            await update_reward(reward_name, stock=stock - 1)
            log_channel = discord.utils.get(interaction.guild.channels, name="redeem_logs")
            await interaction2.response.send_message(f"You redeemed **{reward_name}**!", ephemeral=True)
            if log_channel:
                await log_channel.send(f"{interaction.user.mention} redeemed **{reward_name}**.")

    await interaction.response.send_message("Choose a reward to redeem:", view=RewardMenu(), ephemeral=True)

# Owner Commands

@tree.command(name="give", description="Give points to a user", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
@app_commands.describe(user="User", amount="Amount")
async def give(interaction: discord.Interaction, user: discord.Member, amount: int):
    await add_points(user.id, amount)
    await interaction.response.send_message(f"Gave **{amount}** points to {user.mention}.")

@tree.command(name="give_everyone", description="Give points to everyone", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
@app_commands.describe(amount="Amount to give")
async def give_everyone(interaction: discord.Interaction, amount: int):
    for member in interaction.guild.members:
        if not member.bot:
            await add_points(member.id, amount)
    await interaction.response.send_message(f"Gave **{amount}** points to everyone.")

@tree.command(name="remove_points", description="Remove points from user", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
@app_commands.describe(user="User", amount="Points to remove")
async def remove(interaction: discord.Interaction, user: discord.Member, amount: int):
    current = await get_points(user.id)
    new_amount = max(0, current - amount)
    await set_points(user.id, new_amount)
    await interaction.response.send_message(f"Removed **{amount}** points from {user.mention}.")

@tree.command(name="raw_points", description="Show all members and points", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
async def raw_points(interaction: discord.Interaction):
    data = await get_all_points()
    msg = "**All Points:**\n"
    for uid, pts in data:
        member = interaction.guild.get_member(int(uid))
        name = member.display_name if member else "Unknown"
        msg += f"{name}: {pts}\n"
    await interaction.response.send_message(msg)

@tree.command(name="add_reward", description="Add a reward", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
async def add_reward(interaction: discord.Interaction, name: str, price: int, stock: int):
    await create_reward(name, price, stock)
    await interaction.response.send_message(f"Added reward **{name}**.")

@tree.command(name="add_stock", description="Add stock to a reward", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
async def add_stock(interaction: discord.Interaction, name: str, amount: int):
    reward = await get_reward(name)
    if not reward:
        return await interaction.response.send_message("Reward not found.")
    price, stock = reward
    await update_reward(name, stock=stock + amount)
    await interaction.response.send_message(f"Added **{amount}** stock to **{name}**.")

@tree.command(name="delete_reward", description="Delete a reward", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
async def delete_reward_cmd(interaction: discord.Interaction, name: str):
    await delete_reward(name)
    await interaction.response.send_message(f"Deleted reward **{name}**.")

@tree.command(name="drop", description="Drop points to grab", guild=discord.Object(id=GUILD_ID))
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
                return
            self.claimed = True
            await add_points(interaction2.user.id, amount)
            await interaction2.response.edit_message(content=f"{interaction2.user.mention} picked up **{amount}** points!", view=None)

    await interaction.response.send_message(f"**Dropped {amount} points! First to click gets it!**", view=DropView())

@bot.event
async def on_ready():
    await setup_database()
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Logged in as {bot.user}")

# Start both Flask and bot
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run(KEY)
