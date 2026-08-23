import os
import dotenv
dotenv.load_dotenv()    


OPEN_ROUTER_API_KEY : str = os.getenv('OPEN_ROUTER_API_KEY')
OPEN_ROUTER_MODEL : str = os.getenv('OPEN_ROUTER_MODEL', 'openai/gpt-oss-120b:free')
DATABASE_URL : str = os.getenv('DATABASE_URL', 'sqlite:///app.db')
