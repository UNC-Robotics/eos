Beacon Optimizer
================
The Beacon optimizer combines Bayesian optimization with AI-driven reasoning.
At each sampling step, it probabilistically selects between an acquisition function and an AI model
that reasons about experimental data to suggest new parameters.

How It Works
------------
A weighted coin flip decides which strategy is used:

* **Bayesian**: Uses an acquisition function over a surrogate model.
* **AI**: Sends experimental history and domain constraints to an AI model that reasons about patterns
  and suggests experiments. Suggestions are validated against the domain before being accepted.

If the AI fails, Beacon falls back to Bayesian sampling automatically.
Both strategies share the same result history.

Why Hybrid?
~~~~~~~~~~~
* Bayesian optimizers treat the objective as a black box — AI can apply domain reasoning to make informed jumps.
* AI models can hallucinate — the Bayesian component provides a mathematically grounded baseline.
* The probabilistic mixing lets each strategy compensate for the other's weaknesses.

Setting Up
----------
Modify your experiment's ``optimizer.py`` to return ``BeaconOptimizer``:

:bdg-primary:`optimizer.py`

.. code-block:: python

    from bofire.data_models.acquisition_functions.acquisition_function import qUCB
    from bofire.data_models.enum import SamplingMethodEnum
    from bofire.data_models.features.continuous import ContinuousOutput, ContinuousInput
    from bofire.data_models.objectives.identity import MinimizeObjective

    from eos.optimization.beacon_optimizer import BeaconOptimizer
    from eos.optimization.abstract_sequential_optimizer import AbstractSequentialOptimizer


    def eos_create_campaign_optimizer() -> tuple[dict, type[AbstractSequentialOptimizer]]:
        constructor_args = {
            "inputs": [
                ContinuousInput(key="mix_colors.cyan_volume", bounds=(0, 25)),
                ContinuousInput(key="mix_colors.cyan_strength", bounds=(2, 100)),
                ContinuousInput(key="mix_colors.magenta_volume", bounds=(0, 25)),
                ContinuousInput(key="mix_colors.magenta_strength", bounds=(2, 100)),
            ],
            "outputs": [
                ContinuousOutput(key="score_color.loss", objective=MinimizeObjective(w=1.0)),
            ],
            "constraints": [],
            "acquisition_function": qUCB(beta=1),
            "num_initial_samples": 2,
            "initial_sampling_method": SamplingMethodEnum.SOBOL,
            "p_bayesian": 0.5,
            "p_ai": 0.5,
            "ai_model": "claude-agent-sdk:sonnet",
            "ai_model_settings": {
                "effort": "high",
            },
            "ai_additional_context": "The loss is euclidean distance of RGB components.",
        }

        return constructor_args, BeaconOptimizer

.. note::
    Domain parameters (``inputs``, ``outputs``, ``constraints``, etc.) work identically to
    ``BayesianSequentialOptimizer``. See the :doc:`optimizers` page for details.

Parameter Reference
-------------------

Strategy Mix
~~~~~~~~~~~~
The **Bayesian / AI** slider controls the probability of each strategy at each sampling step.
Default is 50/50. Fully **AI** makes Beacon AI-driven; fully **Bayesian** disables the AI agent.

AI Model
~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Field
     - Default
     - Description
   * - **Model**
     - ``claude-agent-sdk:sonnet``
     - Select from the dropdown or type a custom ``provider:model`` value.
   * - **Model Settings**
     - (empty)
     - JSON settings, e.g., ``{"temperature": 0.3}``.
   * - **Retries**
     - ``3``
     - Max retries for invalid AI suggestions.

**Model** examples:

* ``claude-agent-sdk:sonnet`` — Claude Sonnet via Agent SDK **(recommended)**
* ``anthropic:claude-sonnet-4-6`` — Claude Sonnet 4.6 (requires ``ANTHROPIC_API_KEY``)
* ``openai:gpt-5.4`` — GPT-5.4 (requires ``OPENAI_API_KEY``)
* ``google-gla:gemini-3.1-pro-preview`` — Gemini 3.1 Pro (requires ``GOOGLE_API_KEY``)
* ``ollama:qwen3.5:9b`` — Qwen 3.5 9B via Ollama (no API key, see below)

.. tip::
    The ``claude-agent-sdk`` provider is recommended. It uses Claude Code's agentic harness with
    Claude's frontier reasoning capabilities. Authenticates via a Claude subscription
    (``~/.claude`` credentials) or an ``ANTHROPIC_API_KEY``.

AI Context
~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Field
     - Default
     - Description
   * - **History Size**
     - ``50``
     - Number of recent experiments included in the AI prompt.
   * - **Additional Context**
     - (empty)
     - Free-text domain knowledge for the AI.
   * - **Additional Parameters**
     - (empty)
     - Extra result columns shown to the AI as context (not optimized).
       Example: ``analyze_color.red, analyze_color.green, analyze_color.blue``

Claude Agent SDK
----------------
The ``claude-agent-sdk`` provider authenticates via Claude Code CLI credentials (``~/.claude``)
or an ``ANTHROPIC_API_KEY``.

Install the dependency:

.. code-block:: shell

    uv pip install --group claude_agent_sdk

Then set **Model** to ``claude-agent-sdk:sonnet`` (or ``opus``, ``haiku``).

Using Local Models with Ollama
------------------------------
Beacon supports local LLMs via `Ollama <https://ollama.com>`_.

**1. Start Ollama** with sufficient context length:

.. code-block:: shell

    OLLAMA_CONTEXT_LENGTH=32000 ollama serve

**2. Pull a model:**

.. code-block:: shell

    ollama pull qwen3.5:9b

**3. Configure** in the web UI:

* **Model** — ``ollama:qwen3.5:9b``
* **Model Settings** — ``{"temperature": 0.3}``


Runtime Parameters
------------------
These can be changed at runtime via the REST API or the web UI without restarting a campaign:
strategy mix, history size, and additional context.

Expert Insights
~~~~~~~~~~~~~~~
Send domain knowledge to the AI agent during a running campaign via the web UI or REST API:

.. code-block:: shell

    curl -X POST http://localhost:8070/campaigns/my_campaign/optimizer/insight \
      -H "Content-Type: application/json" \
      -d '{"insight": "High mixing speed causes foaming, avoid values above 180."}'

Insights are included in the next AI prompt and persisted across campaign resumes.