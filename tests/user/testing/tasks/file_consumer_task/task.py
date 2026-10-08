from pydantic import BaseModel

from eos import File, Param, task


class FileConsumerOutputs(BaseModel):
    length: int = Param(desc="Number of bytes read from the input file.")


@task("File Consumer")
async def file_consumer(input: File = Param(desc="The file to read.")) -> FileConsumerOutputs:  # noqa: A002
    """Reads an input file and reports its length."""
    return FileConsumerOutputs(length=len(await input.read()))
