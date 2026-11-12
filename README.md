# quant-gpt
quant

## Build and run

This repository currently contains only this README. There is no application
source, dependency manifest, build script, or test suite yet, so there is nothing
to install, compile, or run. Run future build commands from the repository root.
When application code is added, document the required runtime versions,
dependency installation, build, run, and test commands here alongside that code.

## What needs to be rebuilt after a change?

There are no generated artifacts in the current project. Use this checklist as
the application is introduced, and replace it with the actual project commands:

| Change | Required action |
| --- | --- |
| README or other documentation | No application rebuild. |
| Application source | Run the build for the affected application, if it has a compilation step, then restart it. An interpreted application generally only needs a restart; a development server with reload enabled may handle source changes automatically. |
| Dependency manifest or lockfile | Install the updated dependencies, then rebuild and restart the affected application. |
| Build configuration or generated-code inputs | Rerun the relevant generation and build steps, then restart the affected application. |
| Runtime environment variables or API credentials | Restart the process so it reads the new values. Rebuild only if the application embeds those variables at build time. |
| Container image definition or files copied into an image | Rebuild the image and recreate the container. Runtime-only environment changes generally require recreating the container without rebuilding the image. |

## Alpaca credentials

Configure these names in the cloud environment settings, with the corresponding
credential in each variable's **value** field:

- `APCA_API_KEY_ID`: Alpaca key ID.
- `APCA_API_SECRET_KEY`: matching Alpaca secret key.
- `APCA_API_BASE_URL`: `https://paper-api.alpaca.markets` for paper trading,
  if the future application uses this variable to choose its endpoint.

Do not use an API key as the variable name or commit credentials to the
repository. The cloud network allowlist must permit the chosen Alpaca hostname
before requests can reach it. A read-only `GET /v2/account` on the selected
trading endpoint can verify authentication without placing orders. HTTP 200
confirms authentication; a proxy connection denial does not establish whether
the credentials are valid. Paper and live trading use different credentials
and endpoints.
