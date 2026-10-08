from eos import task


@task("Log UV-Vis Data")
async def log_uv_vis_data() -> None:
    """Persist the scan vector to the data store."""
