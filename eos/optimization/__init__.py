import os
import warnings

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")  # Keep the pydantic-ai setup banner out of optimizer logs

# Ignore warnings from bofire
warnings.filterwarnings("ignore", category=UserWarning, module="bofire.utils.cheminformatics")
warnings.filterwarnings("ignore", category=UserWarning, module="bofire.surrogates.xgb")
warnings.filterwarnings("ignore", category=UserWarning, module="bofire.strategies.predictives.enting")
