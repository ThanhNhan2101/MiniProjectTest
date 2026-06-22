
import environ
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

# Initialize environment variables
env = environ.Env(
    # Set default values for environment variables
    DEBUG=(bool, False)
)
# Set the project base directory: /app
BASE_DIR = Path(__file__).resolve().parent.parent

# Read the .env file
environ.Env.read_env(BASE_DIR / ".env")


def env_to_enum(enum_cls, value):
    try:
        return next(x for x in enum_cls if x.value == value)
    except StopIteration:
        raise ImproperlyConfigured(
            f"Value {repr(value)} not found in {enum_cls.__name__}")
