import random
import string

from pydantic import BaseModel

from eos import Param, task


class FileGenerationOutputs(BaseModel):
    file: bytes = Param(file_name="file.txt", desc="The generated file.")


@task("File Generation")
async def file_generation(
    content_length: int = Param(10, min=0, desc="How many characters to generate in the file."),
) -> FileGenerationOutputs:
    """Generates a file with random data."""
    content = "".join(random.choices(string.ascii_letters + string.digits, k=content_length))
    return FileGenerationOutputs(file=content.encode())
