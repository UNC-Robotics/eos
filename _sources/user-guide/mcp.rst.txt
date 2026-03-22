MCP Server
==========
EOS exposes a `Model Context Protocol <https://modelcontextprotocol.io>`_ (MCP) server through its web UI.
This allows AI assistants like Claude to interact with EOS directly, querying experiments, submitting campaigns, inspecting devices, and more.

Once connected, the AI assistant automatically discovers all available tools. You can ask it to do things like
"check the status of my campaign", "submit 10 multiplication experiments", or "what functions does the pipette support?"

.. warning::

    The MCP endpoint currently has no authentication.
    Only expose it in trusted environments (local network or behind a reverse proxy with auth).


Connecting
----------

The MCP server is available at ``http://<web-ui-host>:3000/api/mcp`` using the Streamable HTTP transport.

Claude Code
~~~~~~~~~~~

.. code-block:: bash

    claude mcp add EOS http://localhost:3000/api/mcp --transport http

Claude Desktop
~~~~~~~~~~~~~~

Add to your ``claude_desktop_config.json``:

.. code-block:: json

    {
      "mcpServers": {
        "EOS": {
          "url": "http://localhost:3000/api/mcp",
          "transport": "streamable-http"
        }
      }
    }

Other MCP Clients
~~~~~~~~~~~~~~~~~

Point any MCP-compatible client to ``http://localhost:3000/api/mcp`` with the **Streamable HTTP** transport.
Replace ``localhost:3000`` with your web UI host and port if different.


Capabilities
------------

The MCP server exposes 50 tools across the following categories:

* **Campaigns, Experiments, Tasks** -- List, inspect, submit, and cancel at every level of the execution hierarchy.
* **Definitions** -- Browse loaded task types, device types, lab layouts, and experiment workflows.
* **Management** -- Load, unload, and reload labs, experiments, devices, and packages.
* **Optimizer** -- Query optimizer state, update runtime parameters, and provide expert insights.
* **Devices** -- List devices, inspect state, discover available RPC functions, and call them directly.
* **SQL** -- Run read-only queries against the EOS database.
* **Filesystem** -- Browse packages and read entity configuration files (YAML, Python).


Examples
--------

These examples show natural language prompts you might give an AI assistant connected to EOS via MCP.

.. code-block:: text

    "Show me the status of the catalyst_screening campaign and list all completed experiments"

    "Submit a color mixing experiment targeting RGB(120, 45, 200) with ink dispensing and UV-Vis analysis"

    "What devices are available in the wet lab? What functions does the liquid handler support?"

    "How did the yield change across the last 10 experiments in the solubility campaign?"

    "Reload the experiment definitions, I just updated the YAML for the pH optimization workflow"
