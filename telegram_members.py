import os
import asyncio
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession

# ==========================================
# LOAD SECRETS FROM ENVIRONMENT VARIABLES
# ==========================================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# For a Bot, we use an empty StringSession.
client = TelegramClient(StringSession(), API_ID, API_HASH)

# Number of members to show per page
ITEMS_PER_PAGE = 25

def build_page(page_num, results, target_name):
    """Builds the text and the navigation buttons for a specific page."""
    start_idx = page_num * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_items = results[start_idx:end_idx]
    
    total_pages = (len(results) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    
    # Normal text UI
    text = f"📊 Members from {target_name}\n"
    text += f"(Page {page_num + 1} of {total_pages})\n\n"
    
    for item in page_items:
        text += f"{item}\n"
        
    # Inline navigation buttons
    buttons = []
    if page_num > 0:
        buttons.append([Button.inline("⬅️ Previous Page", data=f"page_{page_num - 1}")])
    if page_num < total_pages - 1:
        buttons.append([Button.inline("Next Page ➡️", data=f"page_{page_num + 1}")])
        
    return text, buttons

# Listen for the /scrape command
@client.on(events.NewMessage(pattern=r'(?i)^/scrape (.+)'))
async def scrape_command(event):
    targets_raw = event.pattern_match.group(1)
    targets = [t.strip() for t in targets_raw.split(',') if t.strip()]

    if not targets:
        await event.reply("Please provide at least one target. Example: /scrape @group1, @group2")
        return

    for target in targets:
        status_msg = await event.reply(f"🔄 Fetching members for: {target}...")
        
        try:
            entity = await client.get_entity(target)
        except Exception as e:
            await status_msg.edit(f"❌ Failed to access {target}.\nError: {e}\n\nMake sure the bot is added to a Group and promoted to Admin. Bots cannot scrape Channels.")
            continue

        lines = []
        count = 0
        
        try:
            # BOTS ARE LIMITED TO 200 MEMBERS by Telegram
            async for user in client.iter_participants(entity, limit=200):
                if user.deleted or user.bot:
                    continue
                
                # Bots cannot see statuses. It will always be "Hidden".
                status_str = "Hidden (Bot Restriction)"
                
                # Check if they have a username
                if user.username:
                    display_name = f"@{user.username}"
                else:
                    first_name = user.first_name or "Unknown"
                    display_name = f'<a href="tg://user?id={user.id}">{first_name}</a>'
                
                # Format: Name | Status
                lines.append(f"👤 {display_name} | Status: {status_str}")
                count += 1
        except Exception as e:
            await status_msg.edit(f"❌ Failed to fetch members.\nError: {e}\n\nRemember: Bots can only scrape Groups (max 200 members) where the bot is Admin.")
            continue

        if count == 0:
            await status_msg.edit(f"⚠️ No valid members found in {target}.")
            continue

        # Store results for pagination
        client._scrape_results = lines
        client._scrape_target = target

        # Build and send the first page
        text, buttons = build_page(0, lines, target)
        
        # Use html parse mode for clickable links
        await status_msg.edit(text, buttons=buttons, parse_mode='html')


@client.on(events.CallbackQuery)
async def button_handler(event):
    """Handles the Previous/Next button clicks."""
    await event.answer()  
    
    data = event.data.decode('utf-8')
    if not data.startswith("page_"):
        return
        
    page_num = int(data.split("_")[1])

    member_list = getattr(client, '_scrape_results', [])
    target = getattr(client, '_scrape_target', '')

    if not member_list:
        await event.edit("⚠️ Data expired. Please run /scrape again.")
        return

    text, buttons = build_page(page_num, member_list, target)
    await event.edit(text, buttons=buttons, parse_mode='html')


async def main():
    print("Bot is starting...")
    
    # Log in using the Bot Token
    await client.start(bot_token=BOT_TOKEN)
    print("Bot is running! Go to Telegram and send /scrape @groupname to your bot.")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())