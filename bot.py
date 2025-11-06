import sys
import discord
import os
import datetime
import aiohttp
import asyncio
import json
from discord.ext import commands, tasks
from cryptography.fernet import Fernet
from discord.ext import commands
from discord import ui, File
from discord.ext import tasks
from io import StringIO
from discord import ui
import logging
from datetime import datetime

import os

TOKEN = os.getenv("DISCORD_TOKEN")

CATEGORY_PROBLEME_BOUTIQUE_ID = int(os.getenv("CATEGORY_PROBLEME_BOUTIQUE_ID"))
CATEGORY_PLAINTE_STAFF_ID   = int(os.getenv("CATEGORY_PLAINTE_STAFF_ID"))
CATEGORY_MORT_RP_ID         = int(os.getenv("CATEGORY_MORT_RP_ID"))
CATEGORY_PROBLEME_RP_ID     = int(os.getenv("CATEGORY_PROBLEME_RP_ID"))
CATEGORY_DOSSIER_LEGAL_ID   = int(os.getenv("CATEGORY_DOSSIER_LEGAL_ID"))
CATEGORY_DOSSIER_ILLEGAL_ID = int(os.getenv("CATEGORY_DOSSIER_ILLEGAL_ID"))
CATEGORY_REMBOURSEMENT_ID   = int(os.getenv("CATEGORY_REMBOURSEMENT_ID"))
CATEGORY_BUGS_ID             = int(os.getenv("CATEGORY_BUGS_ID"))
CATEGORY_BANS_ID             = int(os.getenv("CATEGORY_BANS_ID"))
CATEGORY_WIPE_ID             = int(os.getenv("CATEGORY_WIPE_ID"))
CATEGORY_AUTRES_ID           = int(os.getenv("CATEGORY_AUTRES_ID"))

ROLE_TEAM_IDS = [int(x) for x in os.getenv("ROLE_TEAM_IDS").split(",")]

LOGS_CHANNEL_ID             = int(os.getenv("LOGS_CHANNEL_ID"))
AUTO_ROLE_ID                = int(os.getenv("AUTO_ROLE_ID"))
PING_ROLE_ID                = int(os.getenv("PING_ROLE_ID"))
TICKET_REMINDER_CHANNEL_ID  = int(os.getenv("TICKET_REMINDER_CHANNEL_ID"))



intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


CATEGORY_ID = config.get("category_id")
TEAM_ROLE_IDS = config.get("role_team_ids", [])
LOGS_CHANNEL_ID = config.get("logs_channel_id")
AUTO_ROLE_ID = config.get("auto_role_id")
PING_ROLE_ID = config.get("ping_role_id")

FIVEM_IP = "82.67.2.57"
FIVEM_PORT = "30120"


@tasks.loop(seconds=60)
async def update_status():
    players_url = f"http://{FIVEM_IP}:{FIVEM_PORT}/players.json"
    info_url = f"http://{FIVEM_IP}:{FIVEM_PORT}/info.json"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(players_url) as resp:
                if resp.status != 200:
                    raise Exception("Erreur récupération joueurs")
                text = await resp.text()
                players = json.loads(text)
                player_count = len(players)

            async with session.get(info_url) as resp:
                if resp.status != 200:
                    raise Exception("Erreur récupération info")
                text = await resp.text()
                info = json.loads(text)
                max_players = int(info.get("vars", {}).get("sv_maxClients", 2048))

            await bot.change_presence(activity=discord.Game(
                name=f"En Ligne : {player_count}/{max_players}"
            ))

    except Exception as e:
        print("Erreur :", e)
        await bot.change_presence(activity=discord.Game(name="serveur OFF"))


@bot.event
async def on_member_join(member):
    auto_role_id = config.get("auto_role_id")
    if auto_role_id:
        role = member.guild.get_role(auto_role_id)
        if role:
            try:
                await member.add_roles(role, reason="Attribution automatique à l'arrivée")
                print(f"✅ Rôle {role.name} attribué à {member.name}")
            except discord.Forbidden:
                print("❌ Permission refusée pour ajouter le rôle.")

    
    logging.basicConfig(level=logging.INFO)


pending_premium_tasks: dict[int, asyncio.Task] = {}


async def _premium_timeout_handler(channel_id: int, timeout: int = 300):
    """Wait `timeout` seconds; if the modal wasn't submitted, close the ticket channel."""
    try:
        await asyncio.sleep(timeout)
        task = pending_premium_tasks.get(channel_id)
        if task is None:
            return

        channel = bot.get_channel(channel_id)
        if channel is None:
            pending_premium_tasks.pop(channel_id, None)
            return

        try:
            await channel.send("The premium form was not submitted in time. This ticket will close in 10 seconds.")
        except Exception:
            logging.exception("_premium_timeout_handler: failed to notify about closure")

        await asyncio.sleep(10)
        try:
            await channel.delete()
        except Exception:
            logging.exception("_premium_timeout_handler: failed to delete channel")

        pending_premium_tasks.pop(channel_id, None)
    except asyncio.CancelledError:
        
        return
    except Exception:
        logging.exception("_premium_timeout_handler top-level error")


def _excepthook(exc_type, exc, tb):
    logging.exception("Uncaught exception", exc_info=(exc_type, exc, tb))


sys.excepthook = _excepthook


def _loop_exception_handler(loop, context):
    logging.error("Event loop exception: %s", context)
    try:
        exc = context.get('exception')
        if exc:
            logging.exception("Loop exception", exc_info=exc)
    except Exception:
        logging.exception("Exception in loop exception handler")


try:
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(_loop_exception_handler)
except Exception:
    logging.warning("Could not set loop exception handler")


class CloseButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="🔒 Fermer le ticket", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await interaction.response.send_message("Fermeture du ticket dans 2 secondes...", ephemeral=True)
        except Exception:
            logging.exception("CloseButton: failed to send ephemeral ack")
        await asyncio.sleep(2)
        try:
            await interaction.channel.delete()
        except Exception:
            logging.exception("CloseButton: failed to delete channel")


class TicketTypeSelect(ui.Select):
    def __init__(self, author):
        self.author = author
        options = [
            discord.SelectOption(label="🔧Bugs", value="bug", description="bug ig", emoji="🔧"),
            discord.SelectOption(label="💎Remboursement", value="remboursement", description="remboursement d'achats/perte bug", emoji="💎"),
            discord.SelectOption(label="💭Autres", value="autre", description="autre probleme", emoji="💭")
        ]
        super().__init__(placeholder="Type de ticket...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            try:
                await interaction.response.send_message("Seul l'auteur du ticket peut choisir le type.", ephemeral=True)
            except Exception:
                logging.exception("TicketTypeSelect: failed to notify non-author")
            return

        ticket_type = self.values[0]
        msg = {
            "support": "Describe your problem here and a staff member will help you.",
            "remboursement": ("Premium packages available:\n"
                        "• Starter — $2.99\n"
                        "• Standard — $4.99\n"
                        "• Pro — $10.99\n\n"
                        "Please complete the form. Payment info will be provided in the form embed."),
            "other": "Thank you for your request. Please explain your need here."
        }

        try:
            if ticket_type == "remboursement":
                
                try:
                    
                    await interaction.channel.send(msg[ticket_type], view=PremiumCloseView())
                except Exception:
                    logging.exception("TicketTypeSelect: failed to send premium info message")

                
                try:
                    await interaction.message.delete()
                except Exception:
                    logging.debug("TicketTypeSelect: failed to delete original select message (maybe already deleted)")

                
                try:
                    await interaction.response.send_modal(PremiumFormModal(channel_id=interaction.channel.id))
                    
                    chan_id = interaction.channel.id if interaction.channel else None
                    if chan_id:
                        
                        old = pending_premium_tasks.get(chan_id)
                        if old and not old.done():
                            old.cancel()
                        pending_premium_tasks[chan_id] = asyncio.create_task(_premium_timeout_handler(chan_id, timeout=300))
                except Exception:
                    logging.exception("TicketTypeSelect: failed to send premium modal")

                
                return
            else:
                await interaction.channel.send(msg[ticket_type], view=CloseButton())
        except Exception:
            logging.exception("TicketTypeSelect: failed to send follow-up message/view")

        try:
            await interaction.message.delete()
        except Exception:
            logging.debug("TicketTypeSelect: failed to delete original select message (maybe already deleted)")


class TicketTypeView(ui.View):
    def __init__(self, author):
        super().__init__(timeout=None)
        self.add_item(TicketTypeSelect(author))


class TicketButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="📩 Contact-us", style=discord.ButtonStyle.blurple, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: ui.Button):
        guild = interaction.guild
        author = interaction.user

        category = discord.utils.get(guild.categories, name="Tickets")
        if category is None:
            category = await guild.create_category("Tickets")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }

        channel = await guild.create_text_channel(f"ticket-{author.name}", overwrites=overwrites, category=category)

        embed = discord.Embed(
            title="Choisissez le type de ticket",
            description="Merci de sélectionner le type de demande ci-dessous.",
            color=discord.Color.blue()
        )
        view = TicketTypeView(author)
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"Ticket créé : {channel.mention}", ephemeral=True)


class PremiumFormModal(ui.Modal):
    def __init__(self, channel_id: int | None = None):
        super().__init__(title="Premium Purchase Form")
        self.target_channel_id = channel_id

        
        self.add_item(ui.TextInput(label="Discord Username", placeholder="e.g. User#1234"))
        self.add_item(ui.TextInput(label="Your PayPal Email", placeholder="e.g. you@paypal.com"))
        self.add_item(ui.TextInput(label="ID discord", placeholder="Your Discord ID"))
        self.add_item(ui.TextInput(label="Month / Year", placeholder="How many months / years"))
        
        self.add_item(ui.TextInput(label="Selected Package", placeholder="Starter $2.99 / Standard $4.99 / Pro $10.99 (monthly packages)", style=discord.TextStyle.short))

    async def callback(self, interaction: discord.Interaction):
        try:
            answers = [field.value for field in self.children]
            
            embed = discord.Embed(
                title="Premium Purchase Request",
                description="A new premium purchase request has been submitted.",
                color=discord.Color.gold(),
                timestamp=datetime.utcnow(),
            )

            
            try:
                embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
            except Exception:
                pass

            questions = [
                "Discord Username",
                "PayPal Email",
                "Discord ID",
                "Duration",
                "Selected Package",
            ]

            for q, a in zip(questions, answers):
                embed.add_field(name=q, value=a or "N/A", inline=False)

            
            embed.add_field(
                name="Payment",
          value=("Please send payment to PayPal: `sinxoppl2@gmail.com` or via [PayPal.me/sinxoppls](https://www.paypal.me/sinxoppls)\n"
              "Available packages: Starter — $2.99 | Standard — $4.99 | Pro — $10.99"),
                inline=False,
            )

            try:
                await interaction.response.send_message("Thanks — your form is being processed.", ephemeral=True)
            except Exception:
                logging.exception("PremiumForm: failed to ack interaction")

           
            target = None
            if getattr(self, 'target_channel_id', None):
                try:
                    target = bot.get_channel(int(self.target_channel_id))
                except Exception:
                    logging.exception("PremiumForm: could not resolve channel from id")

            if target is None:
                target = interaction.channel

            if target is None:
                if getattr(interaction, 'followup', None):
                    try:
                        await interaction.followup.send("Unable to send the request into the ticket. Contact an administrator.", ephemeral=True)
                    except Exception:
                        logging.exception("PremiumForm: failed to notify admin")
                return

         
            try:
                
                try:
                    embed.set_footer(text=f"Channel: {target.name}")
                except Exception:
                    pass

                await target.send(embed=embed)
                try:
                    await interaction.followup.send("Form submitted successfully.", ephemeral=True)
                except Exception:
                    pass
            except Exception:
                logging.exception("PremiumForm: failed to send embed")
                try:
                    with open("errors.log", "a", encoding="utf-8") as ef:
                        ef.write(f"[{__import__('datetime').datetime.utcnow().isoformat()}] Error sending premium embed\n")
                except Exception:
                    logging.exception("PremiumForm: failed to write errors.log")
                try:
                    if getattr(interaction, 'followup', None):
                        await interaction.followup.send("Error sending the form into the ticket. Contact an administrator.", ephemeral=True)
                    else:
                        await interaction.channel.send("Error sending the form. Contact an administrator.")
                except Exception:
                    logging.exception("PremiumForm: failed to notify user about send error")
        except Exception:
            logging.exception("PremiumForm.callback top-level error")
        finally:
            
            try:
                if getattr(self, 'target_channel_id', None):
                    pending = pending_premium_tasks.pop(int(self.target_channel_id), None)
                    if pending and not pending.done():
                        pending.cancel()
            except Exception:
                logging.exception("PremiumForm: failed to cancel pending timeout task")


class PremiumCloseView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="📝 Purchase Form", style=discord.ButtonStyle.green, custom_id="premium_form")
    async def premium_form(self, interaction: discord.Interaction, button: ui.Button):
        channel_id = interaction.channel.id if interaction.channel else None
        try:
            await interaction.response.send_modal(PremiumFormModal(channel_id=channel_id))
        except Exception:
            logging.exception("PremiumCloseView: failed to send modal")

    @ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("Closing the ticket in 2 seconds...", ephemeral=True)
        await asyncio.sleep(2)
        await interaction.channel.delete()


@bot.command()
async def ticket(ctx):
    embed = discord.Embed(
        title="Support Ticket",
        description="Click the button below to open a ticket",
        color=discord.Color.green()
    )
    view = TicketButton()
    await ctx.send(embed=embed, view=view)


def load_config():
    with open("config.json", "r") as f:
        return json.load(f)


@bot.event
async def on_interaction(interaction: discord.Interaction):
    
    try:
        tname = getattr(interaction.type, 'name', None)
        if tname == 'modal_submit' or (isinstance(interaction.data, dict) and interaction.data.get('components')):
            answers = []
            comps = interaction.data.get('components', []) if isinstance(interaction.data, dict) else []
            for row in comps:
                for comp in row.get('components', []) if isinstance(row, dict) else []:
                    try:
                        answers.append(comp.get('value', ''))
                    except Exception:
                        try:
                            answers.append(getattr(comp, 'value', ''))
                        except Exception:
                            answers.append('')

            try:
                embed = discord.Embed(
                    title="Premium Purchase Request",
                    description="A new premium purchase request has been submitted.",
                    color=discord.Color.gold(),
                    timestamp=datetime.utcnow(),
                )

                
                try:
                    if getattr(interaction, 'user', None):
                        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
                except Exception:
                    pass

                questions = [
                    "Discord Username",
                    "PayPal Email",
                    "Discord ID",
                    "Duration",
                    "Selected Package",
                ]

                for q, a in zip(questions, answers):
                    embed.add_field(name=q, value=a or "N/A", inline=False)

                embed.add_field(
                    name="Payment",
              value=("Please send payment to PayPal: `sinxoppl2@gmail.com` or via [PayPal.me/sinxoppls](https://www.paypal.me/sinxoppls)\n"
                  "Available packages: Starter — $2.99 | Standard — $4.99 | Pro — $10.99"),
                    inline=False,
                )
            except Exception:
                logging.exception("Fallback failed to build embed")
                return

            try:
                await interaction.response.send_message("Merci, votre formulaire est en cours de traitement...", ephemeral=True)
            except Exception:
                logging.exception("Fallback failed to ack modal")

            target = interaction.channel
            if target is None:
                logging.error("Fallback: no channel to send modal results")
                return

            try:
                await target.send(embed=embed)
                
                try:
                    pending = pending_premium_tasks.pop(int(target.id), None)
                    if pending and not pending.done():
                        pending.cancel()
                except Exception:
                    logging.exception("Fallback: failed to cancel pending timeout task")
            except Exception:
                logging.exception("Fallback failed to send embed")
            return
    except Exception:
        logging.exception("Fallback on_interaction error")


@bot.event
async def on_ready():
    print(f"{bot.user} est connecté !")
    update_status.start()
    bot.add_view(TicketButton())
    bot.add_view(CloseButton())
    bot.add_view(PremiumCloseView())
    send_auto_ticket.start()


last_auto_ticket_message = None


@tasks.loop(minutes=25)
async def send_auto_ticket():
    global last_auto_ticket_message
    try:
        config = load_config()
    except Exception:
        return
    channel_id = int(config.get("auto_ticket_channel_id", 0))
    if not channel_id:
        return
    channel = bot.get_channel(channel_id)
    if channel:
        if last_auto_ticket_message:
            try:
                await last_auto_ticket_message.delete()
            except Exception:
                pass
        embed = discord.Embed(title="Support Ticket", description="Click the button below to open a ticket", color=discord.Color.green())
        view = TicketButton()
        last_auto_ticket_message = await channel.send(embed=embed, view=view)


@bot.event
async def on_error(event_method, *args, **kwargs):
    logging.exception("on_error fired for %s", event_method)

bot.run(config["token"])
