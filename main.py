from bot import Bot
from database import initialize_database

if __name__ == "__main__":
    # First, initialize the database connection. This prevents import errors.
    initialize_database()
    
    # Then, create and run the bot instance.
    app = Bot()
    app.run()
