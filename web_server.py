import asyncio
from aiohttp import web
from plugins import web_server
from config import Config

async def main():
    app_runner = web.AppRunner(await web_server())
    await app_runner.setup()
    bind_address = "0.0.0.0"
    site = web.TCPSite(app_runner, bind_address, Config.PORT)
    await site.start()
    print(f"Web server started on {bind_address}:{Config.PORT}")
    await asyncio.Event().wait() # Keep it running

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Web server stopped.")
