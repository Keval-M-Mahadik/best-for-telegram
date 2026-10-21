import os
import asyncio
from aiohttp import web
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError

# ==========================================
# LOAD SECRETS FROM ENVIRONMENT VARIABLES
# ==========================================
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# 🛠️ FIX: Added connection_retries, retry_delay, timeout, and flood_sleep_threshold
# This prevents the bot from freezing when Telegram rate-limits it or network drops.
client = TelegramClient(
    StringSession(), 
    API_ID, 
    API_HASH,
    connection_retries=10,    # Retry connection up to 10 times if it drops
    retry_delay=3,            # Wait 3 seconds between retries
    request_retries=5,        # Retry requests 5 times
    flood_sleep_threshold=60, # Automatically sleep and wait if Telegram says "FloodWait" (up to 60 seconds)
    timeout=30                # Give up if a request takes longer than 30 seconds
)

# Number of members to show per page
ITEMS_PER_PAGE = 25

# Dummy web server to keep Render Web Service alive
async def handle(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080)) 
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started on port {port}")

def build_page(page_num, results, target_name):
    start_idx = page_num * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_items = results[start_idx:end_idx]
    total_pages = (len(results) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    
    text = f"📊 Members from {target_name}\n(Page {page_num + 1} of {total_pages})\n\n"
    for item in page_items:
        text += f"{item}\n"
        
    buttons = []
    if page_num > 0:
        buttons.append([Button.inline("⬅️ Previous Page", data=f"page_{page_num - 1}")])
    if page_num < total_pages - 1:
        buttons.append([Button.inline("Next Page ➡️", data=f"page_{page_num + 1}")])
        
    return text, buttons

@client.on(events.NewMessage(pattern=r'(?i)^/scrape (.+)'))
async def scrape_command(event):
    targets_raw = event.pattern_match.group(1)
    targets = [t.strip() for t in targets_raw.split(',') if t.strip()]

    for target in targets:
        status_msg = await event.reply(f"🔄 Fetching members for: {target}...\n*(If the group is large, this may take a moment)*")
        
        try:
            # Use get_entity to resolve the group/username
            entity = await client.get_entity(target)
        except FloodWaitError as e:
            await status_msg.edit(f"⏳ Telegram rate limit reached. Please wait {e.seconds} seconds and try again.")
            continue
        except Exception as e:
            await status_msg.edit(f"❌ Failed to access {target}.\nError: {e}\n\nMake sure the bot is added to a Group and promoted to Admin.")
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
                
                if user.username:
                    display_name = f"@{user.username}"
                else:
                    first_name = user.first_name or "Unknown"
                    display_name = f'<a href="tg://user?id={user.id}">{first_name}</a>'
                
                lines.append(f"👤 {display_name} | Status: {status_str}")
                count += 1
                
        except FloodWaitError as e:
            await status_msg.edit(f"⏳ Telegram rate limit reached while fetching. Please wait {e.seconds} seconds and try again.")
            continue
        except Exception as e:
            await status_msg.edit(f"❌ Failed to fetch members.\nError: {e}")
            continue

        if count == 0:
            await status_msg.edit(f"⚠️ No valid members found in {target}.")
            continue

        client._scrape_results = lines
        client._scrape_target = target

        text, buttons = build_page(0, lines, target)
        await status_msg.edit(text, buttons=buttons, parse_mode='html')

@client.on(events.CallbackQuery)
async def button_handler(event):
    await event.answer()  
    data = event.data.decode('utf-8')
    if not data.startswith("page_"): return
        
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
    
    # Start the dummy web server for Render
    await start_web_server()
    
    # Start the bot
    await client.start(bot_token=BOT_TOKEN)
    print("Bot is running!")
    
    # Keep the bot running forever
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
