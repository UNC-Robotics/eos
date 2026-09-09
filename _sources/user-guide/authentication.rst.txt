Authentication & Authorization
==============================
EOS supports optional authentication and authorization backed by `Zitadel <https://zitadel.com>`_,
an open-source identity provider. Authentication is disabled by default. In that mode, expose
the REST API, web UI, and MCP endpoint only on trusted networks.

How It Works
------------

Identity
~~~~~~~~
Accounts live in one central Zitadel instance that every EOS instance at an institution can share,
so a person uses a single account everywhere. EOS stores no accounts or passwords. Tokens are
validated locally against Zitadel's JWKS, with no per-request call to Zitadel:

* **Web UI**: OpenID Connect sign-in (authorization code + PKCE).
* **REST API** and **MCP endpoint**: ``Authorization: Bearer <token>`` on every request.

Roles
~~~~~
.. list-table::
   :header-rows: 1

   * - Role
     - Scope
     - Permissions
   * - ``viewer``
     - One instance
     - Read-only
   * - ``submitter``
     - One instance
     - Viewer, plus submit and cancel tasks, protocols, and campaigns, reset resources, and tune optimizers
   * - ``editor``
     - One instance
     - Submitter, plus author task, protocol, and device definitions
   * - ``lab_admin``
     - Specific labs in one instance
     - Editor, plus load protocols, reload devices and task plugins, run the simulator, and device RPC for their labs
   * - ``superuser``
     - One instance
     - Everything, including loading labs and packages and managing users

Roles are cumulative and live in each instance's own database, so one account can be ``superuser``
in one instance and ``viewer`` in another. The token identifies the user. Authorization is local to each instance.

Accounts
~~~~~~~~
There is no self-registration. Superusers create accounts from the Management page's **Users** tab
or ``eos auth create-user``, and the user gets a temporary password to change at first sign-in.
Submitted protocol runs and campaigns are owned by the authenticated user.

Machine Access
~~~~~~~~~~~~~~
Scripts and MCP clients use Zitadel service accounts with either **JWT access tokens** (client
credentials flow, validated locally) or **personal access tokens** (long-lived opaque tokens, handy
for MCP configs, validated by introspection with the EOS API app credentials).

Setup
-----
Deployment is automated. Each path below creates the org, project, both apps, and the
``eos-user-admin`` service user, and is safe to re-run.

**Single box.** ``eos setup`` deploys Zitadel and writes ``.env`` and ``web_ui/.env`` for you.

**Dedicated identity host**, shared by several EOS instances. The standalone deployer needs only
Docker:

.. code-block:: shell

    cd docker/zitadel
    python3 deploy.py --url https://eos-auth.lab.internal --tls-mode internal
    python3 deploy.py --url http://localhost:8080                          # local http

It generates secrets, brings up the stack, provisions everything, and writes ``eos-instance.env``
with the values to paste into each instance. Use ``--ui-url`` to register an instance's web UI
redirect (default ``http://localhost:3000``), re-running with another to add more.

**Existing Zitadel** you already run. Create an instance-admin PAT in its console, then point the
same deployer at it to provision without deploying:

.. code-block:: shell

    python3 deploy.py --issuer https://auth.example.org --admin-pat <PAT>

Afterward the only manual step is granting yourself superuser:
``eos auth create-user <username> <email> --superuser``.

TLS
~~~
The bundled Caddy proxy terminates TLS, so no external reverse proxy is needed. Set
``ZITADEL_TLS_MODE`` (or ``deploy.py --tls-mode``). Published ports follow from
``EOS_AUTH_ISSUER``:

* ``internal`` (recommended for isolated lab networks): a self-signed certificate for the issuer's
  host. Export its root CA and distribute it to every browser and EOS service that reaches Zitadel,
  or JWKS and token fetches fail:
  ``docker compose --profile auth exec zitadel-proxy cat /data/caddy/pki/authorities/local/root.crt``.
* ``custom``: your own certificate at ``docker/zitadel/tls/cert.pem`` and ``tls/key.pem``. Preferred
  when an institutional CA your machines already trust issued it, since it skips the step above.
* ``acme``: automatic Let's Encrypt for a public domain reachable on ports 80 and 443. Set
  ``ZITADEL_ACME_EMAIL``.
* ``none``: plain HTTP, for local development or behind your own TLS proxy.

Configuration reference
~~~~~~~~~~~~~~~~~~~~~~~~
The deployers write these values. Set them by hand only when pointing EOS at a Zitadel you
provisioned yourself. In ``config.yml``, or the matching ``EOS_AUTH_*`` variables in ``.env``:

.. code-block:: yaml

    auth:
      enabled: true
      issuer: https://auth.example.org
      org_id: "<org-id>"
      project_id: "<project-id>"
      service_user_pat: "<eos-user-admin PAT>"
      introspection_client_id: "<EOS API app client id>"
      introspection_client_secret: "<EOS API app client secret>"

    web_api:
      cors_origins: ["https://<ui-host>"]

Zitadel audiences tokens to the project, so ``project_id`` is also the accepted audience.

In ``web_ui/.env``:

.. code-block:: bash

    AUTH_ENABLED=true
    AUTH_SECRET=<random string, e.g. openssl rand -base64 32>
    AUTH_ISSUER=https://auth.example.org
    AUTH_CLIENT_ID=<EOS Web UI app client id>
    AUTH_ORG_ID=<org-id>
    AUTH_PROJECT_ID=<project-id>
    AUTH_PAT=<eos-user-admin PAT>
    AUTH_INTROSPECTION_CLIENT_ID=<EOS API app client id>
    AUTH_INTROSPECTION_CLIENT_SECRET=<EOS API app client secret>

Managing Users from the CLI
---------------------------
The ``eos auth`` CLI mirrors the Users tab. Users can be referenced by username, email, or Zitadel
user ID.

.. code-block:: bash

    eos auth create-user alice alice@example.org [--superuser]
    eos auth list-users
    eos auth deactivate-user alice
    eos auth assign-role alice editor
    eos auth assign-role alice lab_admin --lab color_lab
    eos auth revoke-role alice editor
    eos auth list-roles

Calling the API with a Token
----------------------------
.. code-block:: bash

    # PAT or JWT access token
    curl -H "Authorization: Bearer $TOKEN" https://<eos-host>:8070/api/tasks/types
