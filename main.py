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

@tree.command(name="drop", description="Drop multiple points for fastest users", guild=discord.Object(id=GUILD_ID))
@app_commands.check(is_owner)
@app_commands.describe(
    count="How many separate drops (buttons)",
    amounts="Comma-separated point values (e.g., 10,20,50)",
    show_amounts="Show how much each button gives? (Yes or No)",
    role="Optional role that can claim this drop"
)
async def drop(interaction: discord.Interaction, count: int, amounts: str, show_amounts: str, role: discord.Role = None):
    try:
        drop_values = [int(a.strip()) for a in amounts.split(",")]
    except ValueError:
        return await interaction.response.send_message("Invalid point amounts. Use format: 10,20,30", ephemeral=True)

    if len(drop_values) != count:
        return await interaction.response.send_message(f"You must provide exactly {count} drop values.", ephemeral=True)

    visibility = show_amounts.lower() in ["yes", "true"]
    drop_title = f"**{role.mention} only Drop!**" if role else "**Exida just dropped points!**"

    class MultiDropView(discord.ui.View):
        def __init__(self, values):
            super().__init__(timeout=None)
            self.values = values
            self.claimed_by = set()
            self.claimed_status = [False] * len(values)
            self.message = None

            for i in range(len(values)):
                self.add_item(self.create_button(i))

        def get_status_text(self):
            claimed = sum(self.claimed_status)
            total = len(self.values)
            return f"**{claimed}/{total} claimed**"

        def all_claimed(self):
            return all(self.claimed_status)

        def make_label(self, index):
            if self.claimed_status[index]:
                return f"Claimed ✅"
            if visibility:
                return f"Drop {index+1}: {self.values[index]} pts"
            return f"Drop {index+1}: Mystery ✨"

        def create_button(self, index):
            button = discord.ui.Button(label=self.make_label(index), style=discord.ButtonStyle.green, row=index // 5)

            async def callback(interaction2: discord.Interaction):
                user = interaction2.user

                if role and role not in user.roles:
                    await interaction2.response.send_message(f"Only members with the **{role.name}** role can claim this drop!", ephemeral=True)
                    return

                if user.id in self.claimed_by:
                    await interaction2.response.send_message("You've already picked up a drop from this batch!", ephemeral=True)
                    return

                if self.claimed_status[index]:
                    await interaction2.response.send_message("That drop was already taken!", ephemeral=True)
                    return

                # ⏳ Defer to avoid interaction timeout
                await interaction2.response.defer(ephemeral=True)

                amount = self.values[index]
                self.claimed_status[index] = True
                self.claimed_by.add(user.id)
                points[str(user.id)] = points.get(str(user.id), 0) + amount
                save_json(POINTS_FILE, points)

                await interaction2.followup.send(f"You picked up **{amount} points**!", ephemeral=True)
                await self.update_message()

            button.callback = callback
            return button

        async def update_message(self):
            for i, item in enumerate(self.children):
                item.label = self.make_label(i)
                item.disabled = self.claimed_status[i]
            if self.message:
                await self.message.edit(content=f"{drop_title}\n{self.get_status_text()}", view=self)

    view = MultiDropView(drop_values)
    await interaction.response.send_message(f"{drop_title}\n0/{count} claimed", view=view)
    view.message = await interaction.original_response()


@bot.event
async def on_ready():
    await setup_database()
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Logged in as {bot.user}")

# Start both Flask and bot
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run(KEY)
