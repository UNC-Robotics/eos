Beacon Optimizer
================
Beacon combines a pluggable optimizer with AI reasoning. Each sampling call uses the optimizer
with probability ``p_bayesian`` or the AI with probability ``p_ai``. The probabilities must sum to 1.
The default optimizer is Bayesian, but :doc:`custom_beacon` shows how to replace it.

How Sampling Works
------------------
* The AI receives the domain, protocol context, recent results, best observed results, and queued insights.
  Its suggestions are validated against the domain.
* If the AI call fails, Beacon restores the queued insights and falls back to the plugged-in optimizer.
* All measured results are reported to the plugged-in optimizer, including results from AI suggestions.
  Beacon keeps a recent history and associates AI samples with their journal entries.

Configure Beacon
----------------
Use the factory in :doc:`optimizers`, change its returned class to ``BeaconOptimizer``, and
add Beacon settings to the constructor arguments:

.. code-block:: python

    from eos.optimization.beacon_optimizer import BeaconOptimizer

    # Add these keys to the factory's constructor arguments.
    beacon_settings = {
        "p_bayesian": 0.5,
        "p_ai": 0.5,
        "ai_model": "claude-agent-sdk:sonnet",
        "ai_history_size": 50,
        "ai_additional_context": "Prefer experiments that use less starting material.",
    }

The default Bayesian optimizer still needs ``acquisition_function``. A custom replacement can
omit Bayesian-specific settings. See the complete :doc:`custom_beacon` example.

Settings
--------
.. list-table::
   :header-rows: 1

   * - Constructor key
     - Default
     - Meaning
   * - ``p_bayesian`` / ``p_ai``
     - ``0.5`` / ``0.5``
     - Probability of selecting the plugged-in optimizer or AI. ``p_ai=0`` disables the AI agent.
   * - ``ai_model``
     - ``claude-agent-sdk:sonnet``
     - A ``claude-agent-sdk:MODEL`` or ``ollama:MODEL`` identifier.
   * - ``ai_model_settings``
     - ``None``
     - Model settings dictionary, such as ``{"effort": "high"}`` for Claude Agent SDK.
   * - ``ai_retries``
     - ``3``
     - Retries for invalid AI output.
   * - ``ai_history_size``
     - ``50``
     - Maximum recent result rows included in the AI prompt. Use a positive integer.
   * - ``ai_additional_context``
     - ``None``
     - Free-text domain knowledge.
   * - ``ai_additional_parameters``
     - ``None``
     - Extra ``task.parameter`` values included as AI context, such as ``mult_2.product``.
       Beacon removes these columns before reporting outputs to the inner optimizer.

AI Providers
------------
Claude Agent SDK
~~~~~~~~~~~~~~~~
Install the optional dependency on the optimizer worker:

.. code-block:: shell

    uv sync --group claude_agent_sdk

Use ``claude-agent-sdk:sonnet`` or another model supported by your Claude installation.
Authentication uses Claude Code credentials in ``~/.claude`` or ``ANTHROPIC_API_KEY``.
The optional ``ai_api_key`` constructor argument supplies that API key explicitly.

Ollama
~~~~~~
Start a local model server with enough context for the history you intend to send:

.. code-block:: shell

    OLLAMA_CONTEXT_LENGTH=32000 ollama serve

In another terminal, pull the model:

.. code-block:: shell

    ollama pull qwen3.5:9b

Set ``ai_model`` to ``ollama:qwen3.5:9b``. Optional model settings include
``{"temperature": 0.3}``. Other provider prefixes are rejected when the AI agent is created.

Runtime Changes and Insights
----------------------------
The web UI and REST API can change the strategy mix, history size, additional context, and
custom runtime parameters without restarting the campaign. Updating either probability derives
the other. Setting ``p_ai`` to zero removes the AI agent, and enabling it creates one as needed.

For the default API address:

.. code-block:: shell

    curl -X PUT http://localhost:8070/api/campaigns/my_campaign/optimizer/params \
      -H "Content-Type: application/json" \
      -d '{"p_bayesian": 0.7, "ai_history_size": 20}'

    curl -X POST http://localhost:8070/api/campaigns/my_campaign/optimizer/insight \
      -H "Content-Type: application/json" \
      -d '{"insight": "Prefer smaller starting numbers."}'

Add a bearer token when :doc:`authentication` is enabled. Insights are queued until an AI
suggestion succeeds. The journal, queued insights, and runtime settings persist across resume.
Explicit resume overrides take precedence. See :doc:`campaigns` for the resume lifecycle.

History and Token Use
---------------------
Beacon sends history as a compact table. Domain and campaign context form a stable prompt prefix
that can benefit from provider caching. History size bounds the recent results and attached
reasoning sent to the AI, while the full journal remains available in the web UI.

Claude Agent SDK calls log token usage, cache statistics, and reported cost. Use those logs to
choose a history size that fits the model's context window and your token budget.
