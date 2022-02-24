import random
from models import art

def parse(message: str):
    """Parse a string and return a response.
    """
    if message.startswith("$hello"):
        return 'oink'
    if message.startswith("$ree"):
        return random_response()

def random_response() -> str:
    """Generate a random response

    Returns:
        str: the response
    """
    messages=['youve angered me', 
              'rreeeeee', 
              'oink oink oink',
              'hi there :-(:)'] + art.PigArt.get_pig_art()

    return random.choice(messages)